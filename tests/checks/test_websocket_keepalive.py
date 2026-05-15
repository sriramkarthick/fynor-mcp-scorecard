"""
tests/checks/test_websocket_keepalive.py — Unit tests for WebSocketAdapter
and the keepalive_interval check.

Decision D2 (plan-eng-review 2026-05-15):
  Use a 10-second negotiated keepalive interval. The old design checked for a
  server-sent ping within 60 seconds, but the total pipeline timeout is 45
  seconds — the check could never pass. The fix: send a client PING and measure
  time-to-PONG, with a 10s default interval (overridden by server header).

All WebSocket network calls are mocked — no real WebSocket server required.

Mock strategy: patch websockets.asyncio.client.connect at the adapter level
so no TCP connections are opened. Check functions receive a fully mocked adapter.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from fynor.adapters.websocket import WebSocketAdapter, _parse_keepalive_interval
from fynor.adapters.base import Response
from fynor.checks.websocket.keepalive import check_keepalive_interval


# ---------------------------------------------------------------------------
# Helpers — build a mocked WebSocketAdapter
# ---------------------------------------------------------------------------

def _mock_adapter(
    *,
    keepalive_response: Response | None = None,
    call_response: Response | None = None,
    negotiated_interval: float = 10.0,
) -> WebSocketAdapter:
    """Return a WebSocketAdapter with mocked internal methods."""
    adapter = MagicMock(spec=WebSocketAdapter)
    adapter.target = "ws://api.example.com/ws"
    adapter.timeout = 10.0
    adapter.negotiated_keepalive_interval = negotiated_interval

    default_call = Response(status_code=200, body="pong", latency_ms=30.0)
    adapter.call = AsyncMock(return_value=call_response or default_call)
    adapter._measure_ping_pong = AsyncMock(
        return_value=keepalive_response or _pong_ok_response(latency_ms=200.0)
    )
    return adapter


def _pong_ok_response(latency_ms: float = 200.0) -> Response:
    """Simulates a successful PING→PONG round trip within the interval."""
    return Response(
        status_code=200,
        body={"pong_latency_ms": latency_ms},
        latency_ms=latency_ms,
    )


def _pong_timeout_response() -> Response:
    """Simulates no PONG received within the keepalive interval."""
    return Response(
        status_code=504,
        body=None,
        latency_ms=10_001.0,
        error="timeout: no PONG received within 10.0s keepalive interval",
    )


def _connection_refused_response() -> Response:
    """Simulates a failed WebSocket connection."""
    return Response(
        status_code=503,
        body=None,
        latency_ms=50.0,
        error="ConnectionRefusedError: [Errno 111] Connection refused",
    )


# ---------------------------------------------------------------------------
# check_keepalive_interval — pass cases
# ---------------------------------------------------------------------------

class TestKeepalivePass:

    @pytest.mark.asyncio
    async def test_pong_within_interval_passes(self):
        """PONG within 10s interval → passed=True, score=100."""
        adapter = _mock_adapter(
            keepalive_response=_pong_ok_response(latency_ms=500.0),
            negotiated_interval=10.0,
        )
        result = await check_keepalive_interval(adapter)
        assert result.passed is True
        assert result.score == 100
        assert result.check == "keepalive_interval"

    @pytest.mark.asyncio
    async def test_result_is_pass(self):
        adapter = _mock_adapter(keepalive_response=_pong_ok_response())
        result = await check_keepalive_interval(adapter)
        assert result.result == "pass"

    @pytest.mark.asyncio
    async def test_pong_latency_stored_in_value(self):
        """PONG round-trip latency stored in value for observability."""
        adapter = _mock_adapter(keepalive_response=_pong_ok_response(latency_ms=312.0))
        result = await check_keepalive_interval(adapter)
        assert result.value == pytest.approx(312.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_detail_mentions_interval(self):
        """Detail must mention the negotiated interval so users understand the check."""
        adapter = _mock_adapter(
            keepalive_response=_pong_ok_response(),
            negotiated_interval=10.0,
        )
        result = await check_keepalive_interval(adapter)
        assert "10" in result.detail


# ---------------------------------------------------------------------------
# check_keepalive_interval — fail: no PONG within interval
# ---------------------------------------------------------------------------

class TestKeepaliveFail:

    @pytest.mark.asyncio
    async def test_no_pong_within_interval_fails(self):
        """No PONG within 10s → passed=False, score=0."""
        adapter = _mock_adapter(keepalive_response=_pong_timeout_response())
        result = await check_keepalive_interval(adapter)
        assert result.passed is False
        assert result.score == 0
        assert result.result == "fail"

    @pytest.mark.asyncio
    async def test_connection_refused_fails(self):
        """WebSocket connection refused → fail, score=0."""
        adapter = _mock_adapter(keepalive_response=_connection_refused_response())
        result = await check_keepalive_interval(adapter)
        assert result.passed is False
        assert result.score == 0
        assert result.result == "fail"

    @pytest.mark.asyncio
    async def test_fail_detail_mentions_timeout(self):
        """Timeout detail must explain what happened and what interval was used."""
        adapter = _mock_adapter(
            keepalive_response=_pong_timeout_response(),
            negotiated_interval=10.0,
        )
        result = await check_keepalive_interval(adapter)
        assert "10" in result.detail or "pong" in result.detail.lower() \
               or "timeout" in result.detail.lower()


# ---------------------------------------------------------------------------
# Negotiated interval — server header overrides default
# ---------------------------------------------------------------------------

class TestNegotiatedInterval:

    def test_default_interval_is_10s(self):
        """When no server header, default keepalive interval is 10 seconds."""
        adapter = WebSocketAdapter("ws://example.com/ws")
        assert adapter.negotiated_keepalive_interval == 10.0

    def test_parse_keepalive_interval_from_header(self):
        """X-Keepalive-Interval header overrides the 10s default."""
        headers = {"x-keepalive-interval": "30"}
        assert _parse_keepalive_interval(headers) == 30.0

    def test_parse_keepalive_interval_seconds_suffix(self):
        """Header value may include 's' suffix (e.g. '25s')."""
        headers = {"x-keepalive-interval": "25s"}
        assert _parse_keepalive_interval(headers) == 25.0

    def test_parse_keepalive_interval_missing_header_returns_default(self):
        """Missing header returns the 10s default."""
        assert _parse_keepalive_interval({}) == 10.0

    def test_parse_keepalive_interval_malformed_returns_default(self):
        """Malformed header value returns the 10s default (no crash)."""
        assert _parse_keepalive_interval({"x-keepalive-interval": "not-a-number"}) == 10.0

    def test_parse_keepalive_interval_capped_at_pipeline_timeout(self):
        """Negotiated interval cannot exceed 30s — pipeline timeout is 45s."""
        headers = {"x-keepalive-interval": "9999"}
        assert _parse_keepalive_interval(headers) <= 30.0

    def test_parse_keepalive_interval_floored_at_1s(self):
        """Negotiated interval cannot be zero or negative."""
        headers = {"x-keepalive-interval": "0"}
        assert _parse_keepalive_interval(headers) >= 1.0


# ---------------------------------------------------------------------------
# WebSocketAdapter — async-native (D2)
# ---------------------------------------------------------------------------

class TestAsyncNative:

    def test_call_is_coroutine(self):
        import inspect
        assert inspect.iscoroutinefunction(WebSocketAdapter.call)

    def test_measure_ping_pong_is_coroutine(self):
        import inspect
        assert inspect.iscoroutinefunction(WebSocketAdapter._measure_ping_pong)

    def test_adapter_uses_websockets_not_sync(self):
        """Module must import from websockets (async) not a sync WebSocket library."""
        import inspect
        import fynor.adapters.websocket as ws_module
        source = inspect.getsource(ws_module)
        assert "websockets" in source

    def test_no_fixed_60s_timeout(self):
        """
        The fixed 60-second ping check is gone (D2 root cause).
        No literal '60' should appear in the adapter as a timeout constant.
        """
        import inspect
        import fynor.adapters.websocket as ws_module
        source = inspect.getsource(ws_module)
        # '60' must not appear as a standalone keepalive constant
        # (it may appear in comments explaining the old bug)
        import re
        # Look for numeric literals 60 used as timeouts (not in comments/strings)
        code_lines = [l for l in source.splitlines() if not l.strip().startswith("#")]
        code_only = "\n".join(code_lines)
        assert "= 60" not in code_only and "timeout=60" not in code_only, (
            "Adapter must not use 60s as a keepalive timeout. "
            "Decision D2: use 10s negotiated interval."
        )


# ---------------------------------------------------------------------------
# WebSocketAdapter._parse_ws_target — target format handling
# ---------------------------------------------------------------------------

class TestTargetParsing:

    def test_ws_scheme_accepted(self):
        adapter = WebSocketAdapter("ws://example.com/ws")
        assert adapter.target == "ws://example.com/ws"

    def test_wss_scheme_accepted(self):
        adapter = WebSocketAdapter("wss://example.com/ws")
        assert adapter.target == "wss://example.com/ws"

    def test_http_scheme_converted_to_ws(self):
        """http:// targets are silently converted to ws:// for the WebSocket connection."""
        adapter = WebSocketAdapter("http://example.com/ws")
        assert adapter._ws_uri.startswith("ws://")

    def test_https_scheme_converted_to_wss(self):
        adapter = WebSocketAdapter("https://example.com/ws")
        assert adapter._ws_uri.startswith("wss://")
