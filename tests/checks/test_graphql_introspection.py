"""
tests/checks/test_graphql_introspection.py — Unit tests for check_introspection_enabled.

Decision D12 (plan-eng-review 2026-05-15): introspection disabled → result="na", not "fail".
Disabling introspection is a security best practice. Shopify, GitHub, and Stripe all do it.

No real network calls — all adapter behaviour is mocked.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from fynor.adapters.base import Response
from fynor.adapters.graphql import GraphQLAdapter
from fynor.checks.graphql.introspection import check_introspection_enabled


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adapter(introspect_response: Response) -> GraphQLAdapter:
    """Return a mocked GraphQLAdapter with a fixed introspect() return value."""
    adapter = MagicMock(spec=GraphQLAdapter)
    adapter.target = "https://api.example.com/graphql"
    adapter.introspect = AsyncMock(return_value=introspect_response)
    return adapter


def _schema_response(type_count: int = 12) -> Response:
    """200 response with a valid __schema body."""
    return Response(
        status_code=200,
        body={
            "data": {
                "__schema": {
                    "types": [{"name": f"Type{i}"} for i in range(type_count)]
                }
            }
        },
        latency_ms=80.0,
    )


def _errors_response(message: str = "GraphQL introspection is not allowed") -> Response:
    """200 response with errors array and no data — introspection disabled."""
    return Response(
        status_code=200,
        body={"errors": [{"message": message}]},
        latency_ms=60.0,
    )


def _http_error_response(status_code: int) -> Response:
    """Non-200 HTTP response (400 / 403 / 405)."""
    return Response(
        status_code=status_code,
        body={"message": "Not allowed"},
        latency_ms=40.0,
    )


def _connection_error_response() -> Response:
    """Transport-layer failure."""
    return Response(
        status_code=0,
        body=None,
        latency_ms=10000.0,
        error="timeout after 10.0s",
    )


# ---------------------------------------------------------------------------
# na cases — introspection disabled (D12)
# ---------------------------------------------------------------------------

class TestIntrospectionDisabled:

    @pytest.mark.asyncio
    async def test_400_returns_na_not_fail(self):
        """HTTP 400 on introspection query → result='na', not 'fail'."""
        result = await check_introspection_enabled(_adapter(_http_error_response(400)))
        assert result.result == "na"
        assert result.check == "introspection_enabled"

    @pytest.mark.asyncio
    async def test_403_returns_na(self):
        """HTTP 403 → result='na'."""
        result = await check_introspection_enabled(_adapter(_http_error_response(403)))
        assert result.result == "na"

    @pytest.mark.asyncio
    async def test_405_returns_na(self):
        """HTTP 405 → result='na'."""
        result = await check_introspection_enabled(_adapter(_http_error_response(405)))
        assert result.result == "na"

    @pytest.mark.asyncio
    async def test_errors_array_no_data_returns_na(self):
        """200 + errors array + no data → introspection disabled → result='na'."""
        result = await check_introspection_enabled(_adapter(_errors_response()))
        assert result.result == "na"

    @pytest.mark.asyncio
    async def test_errors_array_includes_error_message_in_detail(self):
        """Error message from server must appear in the detail string."""
        result = await check_introspection_enabled(
            _adapter(_errors_response("Introspection disabled for security"))
        )
        assert result.result == "na"
        assert "Introspection disabled for security" in result.detail

    @pytest.mark.asyncio
    async def test_na_passed_is_true(self):
        """na result must set passed=True (not a failure — good security practice)."""
        result = await check_introspection_enabled(_adapter(_http_error_response(403)))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_na_score_is_zero(self):
        """na checks must have score=0 (excluded from averaging, not counted as 0)."""
        result = await check_introspection_enabled(_adapter(_errors_response()))
        assert result.score == 0


# ---------------------------------------------------------------------------
# pass case — introspection enabled
# ---------------------------------------------------------------------------

class TestIntrospectionEnabled:

    @pytest.mark.asyncio
    async def test_valid_schema_returns_pass(self):
        """200 + __schema with types → result='pass'."""
        result = await check_introspection_enabled(_adapter(_schema_response(type_count=15)))
        assert result.result == "pass"
        assert result.passed is True
        assert result.score == 100

    @pytest.mark.asyncio
    async def test_type_count_stored_in_value(self):
        """The number of schema types must be stored in value for observability."""
        result = await check_introspection_enabled(_adapter(_schema_response(type_count=8)))
        assert result.value == 8

    @pytest.mark.asyncio
    async def test_pass_detail_mentions_security_recommendation(self):
        """Detail for enabled introspection must mention disabling it in production."""
        result = await check_introspection_enabled(_adapter(_schema_response()))
        assert "production" in result.detail.lower() or "security" in result.detail.lower()


# ---------------------------------------------------------------------------
# fail case — connectivity / unexpected error
# ---------------------------------------------------------------------------

class TestConnectionFailure:

    @pytest.mark.asyncio
    async def test_transport_error_returns_fail(self):
        """Connection error → result='fail', passed=False, score=0."""
        result = await check_introspection_enabled(_adapter(_connection_error_response()))
        assert result.result == "fail"
        assert result.passed is False
        assert result.score == 0

    @pytest.mark.asyncio
    async def test_transport_error_detail_mentions_error(self):
        """Transport error detail must reference the actual error message."""
        result = await check_introspection_enabled(_adapter(_connection_error_response()))
        assert "timeout" in result.detail.lower() or "connection" in result.detail.lower()

    @pytest.mark.asyncio
    async def test_unexpected_body_shape_returns_fail(self):
        """200 but body is not a GraphQL envelope → fail."""
        bad_response = Response(status_code=200, body="not json at all", latency_ms=30.0)
        result = await check_introspection_enabled(_adapter(bad_response))
        assert result.result == "fail"
        assert result.passed is False


# ---------------------------------------------------------------------------
# Integration: na propagates through scorer correctly
# ---------------------------------------------------------------------------

class TestScorerIntegration:

    @pytest.mark.asyncio
    async def test_na_result_excluded_from_scorer(self):
        """
        End-to-end: introspection_enabled returning na must not pull down the grade.
        Only tests the CheckResult shape — scorer integration tested in test_scorer_na.py.
        """
        result = await check_introspection_enabled(_adapter(_errors_response()))
        # Confirm the result field is set correctly for the scorer to act on
        assert result.result == "na"
        assert result.check == "introspection_enabled"
