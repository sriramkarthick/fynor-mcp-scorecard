"""
tests/checks/test_timeout.py — Unit tests for check_timeout.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fynor.adapters.base import Response
from fynor.adapters.mcp import MCPAdapter
from fynor.checks.mcp.timeout import check_timeout


def _mcp_adapter(target: str = "https://api.example.com/mcp") -> MCPAdapter:
    adapter = MagicMock(spec=MCPAdapter)
    adapter.target = target
    adapter._auth_token = None
    return adapter


@pytest.mark.asyncio
async def test_fast_response_scores_100():
    """Response ≤ 2000ms → score 100, passed."""
    fast = Response(status_code=200, body={}, latency_ms=500.0)
    with patch("fynor.checks.mcp.timeout._make_tight_adapter") as mock_make:
        tight = AsyncMock()
        tight.call = AsyncMock(return_value=fast)
        mock_make.return_value = tight
        result = await check_timeout(_mcp_adapter())

    assert result.passed is True
    assert result.score == 100
    assert result.value == 500.0
    assert "Fast response" in result.detail


@pytest.mark.asyncio
async def test_slow_response_scores_75():
    """Response 2001ms–5000ms → score 75, passes."""
    slow = Response(status_code=200, body={}, latency_ms=3500.0)
    with patch("fynor.checks.mcp.timeout._make_tight_adapter") as mock_make:
        tight = AsyncMock()
        tight.call = AsyncMock(return_value=slow)
        mock_make.return_value = tight
        result = await check_timeout(_mcp_adapter())

    assert result.passed is True
    assert result.score == 75


@pytest.mark.asyncio
async def test_hard_timeout_scores_0():
    """Hard timeout (error contains 'timeout') → score 0, failed."""
    timed_out = Response(status_code=0, body=None, latency_ms=5000.0, error="timeout after 5s")
    with patch("fynor.checks.mcp.timeout._make_tight_adapter") as mock_make:
        tight = AsyncMock()
        tight.call = AsyncMock(return_value=timed_out)
        mock_make.return_value = tight
        result = await check_timeout(_mcp_adapter())

    assert result.passed is False
    assert result.score == 0
    assert result.value is None
    assert "hard timeout" in result.detail.lower()


@pytest.mark.asyncio
async def test_connection_error_scores_75():
    """Non-timeout connection error → graceful degradation → score 75."""
    conn_err = Response(
        status_code=0, body=None, latency_ms=100.0, error="connection refused"
    )
    with patch("fynor.checks.mcp.timeout._make_tight_adapter") as mock_make:
        tight = AsyncMock()
        tight.call = AsyncMock(return_value=conn_err)
        mock_make.return_value = tight
        result = await check_timeout(_mcp_adapter())

    assert result.passed is True
    assert result.score == 75
    assert "Graceful" in result.detail


@pytest.mark.asyncio
async def test_2000ms_exactly_scores_100():
    """Exactly 2000ms → still scores 100 (≤ threshold)."""
    r = Response(status_code=200, body={}, latency_ms=2000.0)
    with patch("fynor.checks.mcp.timeout._make_tight_adapter") as mock_make:
        tight = AsyncMock()
        tight.call = AsyncMock(return_value=r)
        mock_make.return_value = tight
        result = await check_timeout(_mcp_adapter())

    assert result.score == 100


@pytest.mark.asyncio
async def test_2001ms_scores_75():
    """2001ms → just over threshold → score 75."""
    r = Response(status_code=200, body={}, latency_ms=2001.0)
    with patch("fynor.checks.mcp.timeout._make_tight_adapter") as mock_make:
        tight = AsyncMock()
        tight.call = AsyncMock(return_value=r)
        mock_make.return_value = tight
        result = await check_timeout(_mcp_adapter())

    assert result.score == 75
