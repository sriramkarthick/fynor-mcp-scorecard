"""
tests/checks/test_latency_p95.py — Unit tests for check_latency_p95.

All HTTP calls are mocked at the adapter level. No network required.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from fynor.adapters.base import Response
from fynor.checks.mcp.latency import check_latency_p95, _score_from_p95


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fast_responses(n: int = 20, latency_ms: float = 200.0) -> list[Response]:
    """Return N successful responses with the given latency."""
    return [Response(status_code=200, body={}, latency_ms=latency_ms) for _ in range(n)]


def _error_responses(n: int) -> list[Response]:
    """Return N error responses."""
    return [Response(status_code=0, body=None, latency_ms=50.0, error="timeout") for _ in range(n)]


async def _mock_adapter(responses: list[Response]):
    """Return an AsyncMock adapter whose burst() returns the given responses."""
    adapter = AsyncMock()
    adapter.burst = AsyncMock(return_value=responses)
    return adapter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fast_server_scores_100():
    """P95 ≤ 500ms → score 100, passed."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=300.0))
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert result.score == 100
    assert result.check == "latency_p95"
    assert result.value is not None


@pytest.mark.asyncio
async def test_medium_server_scores_75():
    """P95 ≤ 1000ms → score 75."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=800.0))
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert result.score == 75


@pytest.mark.asyncio
async def test_slow_server_scores_50():
    """P95 ≤ 2000ms → score 50, still passes."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=1800.0))
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert result.score == 50


@pytest.mark.asyncio
async def test_very_slow_server_scores_25():
    """P95 ≤ 3000ms → score 25, fails."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=2500.0))
    result = await check_latency_p95(adapter)
    assert result.passed is False
    assert result.score == 25


@pytest.mark.asyncio
async def test_hanging_server_scores_0():
    """P95 > 3000ms → score 0."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=5000.0))
    result = await check_latency_p95(adapter)
    assert result.passed is False
    assert result.score == 0


@pytest.mark.asyncio
async def test_all_requests_fail_scores_0():
    """All 20 requests fail → insufficient sample → score 0."""
    adapter = await _mock_adapter(_error_responses(20))
    result = await check_latency_p95(adapter)
    assert result.passed is False
    assert result.score == 0
    assert "Insufficient sample" in result.detail


@pytest.mark.asyncio
async def test_partial_failure_with_enough_successes():
    """5 failures but 15 successes → still enough for a valid P95."""
    responses = _fast_responses(15, latency_ms=400.0) + _error_responses(5)
    adapter = await _mock_adapter(responses)
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert result.score == 100
    assert "excluded from P95" in result.detail


@pytest.mark.asyncio
async def test_insufficient_sample_border():
    """9 successes out of 20 → below minimum 10 → score 0."""
    responses = _fast_responses(9, latency_ms=200.0) + _error_responses(11)
    adapter = await _mock_adapter(responses)
    result = await check_latency_p95(adapter)
    assert result.passed is False
    assert result.score == 0


# ---------------------------------------------------------------------------
# Score function unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p95_ms,expected_score", [
    (100.0,  100),
    (500.0,  100),
    (501.0,   75),
    (1000.0,  75),
    (1001.0,  50),
    (2000.0,  50),
    (2001.0,  25),
    (3000.0,  25),
    (3001.0,   0),
    (9999.0,   0),
])
def test_score_function_bands(p95_ms: float, expected_score: int):
    assert _score_from_p95(p95_ms) == expected_score
