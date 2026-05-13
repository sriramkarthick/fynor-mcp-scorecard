"""
tests/checks/test_auth_token.py — Unit tests for check_auth_token.

Critical: secret VALUES must NEVER appear in test output, detail strings,
or log files. Tests verify that header NAMES are logged but values are not.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from fynor.adapters.base import Response
from fynor.adapters.mcp import MCPAdapter
from fynor.checks.mcp.auth import check_auth_token, _score_from_failures


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mcp_adapter(
    call_response: Response,
    unauth_response: Response | None = None,
    target: str = "https://api.example.com/mcp",
) -> MCPAdapter:
    """Return a mocked MCPAdapter for auth tests."""
    adapter = MagicMock(spec=MCPAdapter)
    adapter.target = target
    adapter.call = AsyncMock(return_value=call_response)
    adapter.call_without_auth = AsyncMock(
        return_value=unauth_response or Response(status_code=401, body=None, latency_ms=10.0)
    )
    return adapter


def _clean_response() -> Response:
    return Response(status_code=200, body={}, headers={}, latency_ms=50.0)


def _response_with_headers(headers: dict) -> Response:
    return Response(status_code=200, body={}, headers=headers, latency_ms=50.0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_pass_scores_100():
    """No leakage, 401 on no-auth, no URL secrets → score 100."""
    adapter = _mcp_adapter(
        call_response=_clean_response(),
        unauth_response=Response(status_code=401, body=None, latency_ms=10.0),
    )
    result = await check_auth_token(adapter)
    assert result.passed is True
    assert result.score == 100
    assert result.check == "auth_token"


@pytest.mark.asyncio
async def test_credential_header_in_response_fails():
    """Server leaks x-api-key in response → 1 failure → score 40."""
    adapter = _mcp_adapter(
        call_response=_response_with_headers({"x-api-key": "super-secret-value"}),
        unauth_response=Response(status_code=401, body=None, latency_ms=10.0),
    )
    result = await check_auth_token(adapter)
    assert result.passed is False
    assert result.score == 40
    # CRITICAL: the VALUE must NOT appear in detail
    assert "super-secret-value" not in result.detail
    # The header NAME must appear (for actionability)
    assert "x-api-key" in result.detail.lower()


@pytest.mark.asyncio
async def test_unauthenticated_returns_200_fails():
    """Unauthenticated request returns 200 → 1 failure → score 40."""
    adapter = _mcp_adapter(
        call_response=_clean_response(),
        unauth_response=Response(status_code=200, body={}, latency_ms=10.0),
    )
    result = await check_auth_token(adapter)
    assert result.passed is False
    assert result.score == 40
    assert "200" in result.detail


@pytest.mark.asyncio
async def test_unexpected_auth_status_fails():
    """Unauthenticated request returns 500 → 1 failure → score 40."""
    adapter = _mcp_adapter(
        call_response=_clean_response(),
        unauth_response=Response(status_code=500, body=None, latency_ms=10.0),
    )
    result = await check_auth_token(adapter)
    assert result.passed is False
    assert result.score == 40


@pytest.mark.asyncio
async def test_403_is_acceptable():
    """403 is an acceptable rejection of unauthenticated requests."""
    adapter = _mcp_adapter(
        call_response=_clean_response(),
        unauth_response=Response(status_code=403, body=None, latency_ms=10.0),
    )
    result = await check_auth_token(adapter)
    assert result.passed is True
    assert result.score == 100


@pytest.mark.asyncio
async def test_secret_in_url_params_fails():
    """Target URL with ?api_key=secret → 1 failure → score 40."""
    adapter = _mcp_adapter(
        call_response=_clean_response(),
        unauth_response=Response(status_code=401, body=None, latency_ms=10.0),
        target="https://api.example.com/mcp?api_key=mysecret",
    )
    result = await check_auth_token(adapter)
    assert result.passed is False
    assert result.score == 40
    assert "api_key" in result.detail.lower()
    # Value must not appear
    assert "mysecret" not in result.detail


@pytest.mark.asyncio
async def test_two_failures_score_10():
    """Two failures → score 10."""
    adapter = _mcp_adapter(
        call_response=_response_with_headers({"x-secret": "leaked"}),
        unauth_response=Response(status_code=200, body={}, latency_ms=10.0),
    )
    result = await check_auth_token(adapter)
    assert result.score == 10
    # Secret value still must not appear
    assert "leaked" not in result.detail


@pytest.mark.asyncio
async def test_all_three_failures_score_0():
    """Three failures → score 0 → triggers ADR-02 security cap."""
    adapter = _mcp_adapter(
        call_response=_response_with_headers({"x-secret": "v"}),
        unauth_response=Response(status_code=200, body={}, latency_ms=10.0),
        target="https://api.example.com/mcp?api_key=k",
    )
    result = await check_auth_token(adapter)
    assert result.score == 0
    assert result.passed is False


# ---------------------------------------------------------------------------
# Scoring unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n,expected", [(0, 100), (1, 40), (2, 10), (3, 0), (99, 0)])
def test_score_from_failures(n: int, expected: int):
    assert _score_from_failures(n) == expected
