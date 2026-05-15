"""
tests/checks/test_grpc_reflection.py — Unit tests for GRPCAdapter and reflection check.

Decisions tested:
  D3  (plan-eng-review 2026-05-15): reflection disabled → result="na", not "fail"
  D9  (plan-eng-review 2026-05-15): adapter must use grpc.aio, not sync grpcio

All gRPC network calls are mocked — no real gRPC server required.

Mock strategy: patch grpc.aio.insecure_channel / secure_channel so that
GRPCAdapter never opens a real TCP connection. The check functions receive a
fully mocked adapter so we can test the logic in isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest
import grpc

from fynor.adapters.grpc import GRPCAdapter, _grpc_status_to_http
from fynor.adapters.base import Response
from fynor.checks.grpc.reflection import check_reflection_enabled


# ---------------------------------------------------------------------------
# Helpers — build a GRPCAdapter with a mocked channel
# ---------------------------------------------------------------------------

def _mock_adapter(
    *,
    reflection_response: Response | None = None,
    call_response: Response | None = None,
) -> GRPCAdapter:
    """
    Return a GRPCAdapter whose internal methods are mocked.

    reflection_response: what _call_reflection_service() returns
    call_response:       what call() returns
    """
    adapter = MagicMock(spec=GRPCAdapter)
    adapter.target = "api.example.com:50051"
    adapter.timeout = 10.0
    adapter.grpc_method = None

    default_call = Response(status_code=200, body=b"", latency_ms=40.0)
    adapter.call = AsyncMock(return_value=call_response or default_call)
    adapter._call_reflection_service = AsyncMock(
        return_value=reflection_response or _reflection_ok_response()
    )
    return adapter


def _reflection_ok_response(services: list[str] | None = None) -> Response:
    """Simulate a successful reflection response listing services."""
    services = services or ["grpc.health.v1.Health", "example.MyService"]
    return Response(
        status_code=200,
        body={"services": services},
        latency_ms=30.0,
    )


def _reflection_unimplemented_response() -> Response:
    """Simulate UNIMPLEMENTED — server has no reflection service."""
    return Response(
        status_code=501,   # UNIMPLEMENTED maps to 501
        body=None,
        latency_ms=5.0,
        error="StatusCode.UNIMPLEMENTED",
    )


def _reflection_unavailable_response() -> Response:
    """Simulate UNAVAILABLE — server down or network failure."""
    return Response(
        status_code=503,
        body=None,
        latency_ms=10000.0,
        error="StatusCode.UNAVAILABLE: connection refused",
    )


def _reflection_deadline_exceeded() -> Response:
    """Simulate DEADLINE_EXCEEDED — server exists but reflection timed out."""
    return Response(
        status_code=504,
        body=None,
        latency_ms=10000.0,
        error="StatusCode.DEADLINE_EXCEEDED",
    )


# ---------------------------------------------------------------------------
# check_reflection_enabled — na when reflection disabled (D3)
# ---------------------------------------------------------------------------

class TestReflectionDisabled:

    @pytest.mark.asyncio
    async def test_unimplemented_returns_na(self):
        """UNIMPLEMENTED status → reflection disabled → result='na'."""
        adapter = _mock_adapter(reflection_response=_reflection_unimplemented_response())
        result = await check_reflection_enabled(adapter)
        assert result.result == "na"
        assert result.check == "reflection_enabled"

    @pytest.mark.asyncio
    async def test_na_passed_is_true(self):
        """Disabling reflection is a best practice — must not be treated as failure."""
        adapter = _mock_adapter(reflection_response=_reflection_unimplemented_response())
        result = await check_reflection_enabled(adapter)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_na_score_is_zero(self):
        """na checks have score=0 (excluded from scoring by scorer)."""
        adapter = _mock_adapter(reflection_response=_reflection_unimplemented_response())
        result = await check_reflection_enabled(adapter)
        assert result.score == 0

    @pytest.mark.asyncio
    async def test_na_detail_explains_why(self):
        """Detail must explain that UNIMPLEMENTED means reflection is disabled."""
        adapter = _mock_adapter(reflection_response=_reflection_unimplemented_response())
        result = await check_reflection_enabled(adapter)
        assert "reflection" in result.detail.lower()
        assert "na" in result.detail.lower() or "not applicable" in result.detail.lower() \
               or "disabled" in result.detail.lower()


# ---------------------------------------------------------------------------
# check_reflection_enabled — pass when reflection works
# ---------------------------------------------------------------------------

class TestReflectionEnabled:

    @pytest.mark.asyncio
    async def test_reflection_ok_returns_pass(self):
        """Successful reflection → result='pass', score=100."""
        adapter = _mock_adapter(reflection_response=_reflection_ok_response())
        result = await check_reflection_enabled(adapter)
        assert result.result == "pass"
        assert result.passed is True
        assert result.score == 100

    @pytest.mark.asyncio
    async def test_service_count_stored_in_value(self):
        """Number of discovered services stored in value."""
        adapter = _mock_adapter(
            reflection_response=_reflection_ok_response(["svc.A", "svc.B", "svc.C"])
        )
        result = await check_reflection_enabled(adapter)
        assert result.value == 3

    @pytest.mark.asyncio
    async def test_pass_detail_lists_services(self):
        """Detail should mention the discovered services."""
        adapter = _mock_adapter(
            reflection_response=_reflection_ok_response(["grpc.health.v1.Health"])
        )
        result = await check_reflection_enabled(adapter)
        assert "grpc.health.v1.Health" in result.detail


# ---------------------------------------------------------------------------
# check_reflection_enabled — fail on real errors (not na)
# ---------------------------------------------------------------------------

class TestReflectionFail:

    @pytest.mark.asyncio
    async def test_unavailable_returns_fail(self):
        """UNAVAILABLE (server down) → result='fail', not na."""
        adapter = _mock_adapter(reflection_response=_reflection_unavailable_response())
        result = await check_reflection_enabled(adapter)
        assert result.result == "fail"
        assert result.passed is False
        assert result.score == 0

    @pytest.mark.asyncio
    async def test_deadline_exceeded_returns_fail(self):
        """DEADLINE_EXCEEDED → result='fail'."""
        adapter = _mock_adapter(reflection_response=_reflection_deadline_exceeded())
        result = await check_reflection_enabled(adapter)
        assert result.result == "fail"
        assert result.passed is False


# ---------------------------------------------------------------------------
# GRPCAdapter._grpc_method — grpc_method probe (D3)
# ---------------------------------------------------------------------------

class TestGrpcMethodProbe:

    @pytest.mark.asyncio
    async def test_grpc_method_used_when_provided(self):
        """
        When grpc_method is set and reflection is disabled, the adapter
        should fall back to probing that specific method.
        """
        # check_reflection_enabled falls back to grpc_method probe when na
        reflection_disabled = _reflection_unimplemented_response()
        call_ok = Response(status_code=200, body=b"", latency_ms=25.0)

        adapter = _mock_adapter(
            reflection_response=reflection_disabled,
            call_response=call_ok,
        )
        adapter.grpc_method = "grpc.health.v1.Health/Check"

        result = await check_reflection_enabled(adapter)
        # Reflection disabled but grpc_method probe succeeded → pass
        assert result.result == "pass"
        assert result.passed is True
        adapter.call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_grpc_method_probe_fails_returns_fail(self):
        """
        Reflection disabled + grpc_method probe also fails → result='fail'.
        """
        reflection_disabled = _reflection_unimplemented_response()
        call_fail = Response(
            status_code=503,
            body=None,
            latency_ms=10000.0,
            error="StatusCode.UNAVAILABLE",
        )

        adapter = _mock_adapter(
            reflection_response=reflection_disabled,
            call_response=call_fail,
        )
        adapter.grpc_method = "mypackage.MyService/MyMethod"

        result = await check_reflection_enabled(adapter)
        assert result.result == "fail"
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_no_grpc_method_no_reflection_returns_na(self):
        """
        Reflection disabled + no grpc_method configured → result='na'.
        Cannot determine server health without either signal.
        """
        adapter = _mock_adapter(reflection_response=_reflection_unimplemented_response())
        adapter.grpc_method = None

        result = await check_reflection_enabled(adapter)
        assert result.result == "na"


# ---------------------------------------------------------------------------
# _grpc_status_to_http — status code mapping (D9)
# ---------------------------------------------------------------------------

class TestStatusMapping:

    def test_ok_maps_to_200(self):
        assert _grpc_status_to_http(grpc.StatusCode.OK) == 200

    def test_unimplemented_maps_to_501(self):
        assert _grpc_status_to_http(grpc.StatusCode.UNIMPLEMENTED) == 501

    def test_unavailable_maps_to_503(self):
        assert _grpc_status_to_http(grpc.StatusCode.UNAVAILABLE) == 503

    def test_unauthenticated_maps_to_401(self):
        assert _grpc_status_to_http(grpc.StatusCode.UNAUTHENTICATED) == 401

    def test_permission_denied_maps_to_403(self):
        assert _grpc_status_to_http(grpc.StatusCode.PERMISSION_DENIED) == 403

    def test_deadline_exceeded_maps_to_504(self):
        assert _grpc_status_to_http(grpc.StatusCode.DEADLINE_EXCEEDED) == 504

    def test_unknown_maps_to_500(self):
        assert _grpc_status_to_http(grpc.StatusCode.UNKNOWN) == 500


# ---------------------------------------------------------------------------
# GRPCAdapter — async-native (D9): verify grpc.aio is used, not sync grpcio
# ---------------------------------------------------------------------------

class TestAsyncNative:

    def test_adapter_uses_aio_not_sync(self):
        """
        GRPCAdapter must import from grpc.aio, not grpc (sync).
        Verified by checking the module's imports at import time.
        """
        import fynor.adapters.grpc as grpc_module
        import inspect, grpc.aio

        # The module must reference grpc.aio, confirming async-native design
        source = inspect.getsource(grpc_module)
        assert "grpc.aio" in source, (
            "GRPCAdapter must use grpc.aio (async) not sync grpcio. "
            "Decision D9: sync grpcio blocks the FastAPI event loop."
        )

    def test_call_is_coroutine(self):
        """GRPCAdapter.call must be a coroutine function (async def)."""
        import inspect
        assert inspect.iscoroutinefunction(GRPCAdapter.call)

    def test_get_schema_is_coroutine(self):
        import inspect
        assert inspect.iscoroutinefunction(GRPCAdapter.get_schema)
