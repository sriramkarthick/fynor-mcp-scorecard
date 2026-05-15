"""
tests/checks/test_latency_p95.py — Unit tests for check_latency_p95.

Bands locked in check-implementation-contract.md §1:
  P95 ≤  200ms → 100
  P95 ≤  500ms →  80
  P95 ≤ 1000ms →  60  (pass threshold)
  P95 > 1000ms →   0

All HTTP calls are mocked at the adapter level. No network required.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from fynor.adapters.base import Response
from fynor.checks.mcp.latency import check_latency_p95, _score_from_p95


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fast_responses(n: int = 20, latency_ms: float = 100.0) -> list[Response]:
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
# Behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_very_fast_server_scores_100():
    """P95 ≤ 200ms → score 100, passed."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=150.0))
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert result.score == 100
    assert result.check == "latency_p95"
    assert result.value is not None


@pytest.mark.asyncio
async def test_fast_server_scores_80():
    """P95 ≤ 500ms → score 80, passed."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=400.0))
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert result.score == 80


@pytest.mark.asyncio
async def test_acceptable_server_scores_60():
    """P95 ≤ 1000ms → score 60, still passes (at threshold)."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=1000.0))
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert result.score == 60


@pytest.mark.asyncio
async def test_slow_server_scores_0_fails():
    """P95 > 1000ms → score 0, fails."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=1500.0))
    result = await check_latency_p95(adapter)
    assert result.passed is False
    assert result.score == 0


@pytest.mark.asyncio
async def test_hanging_server_scores_0():
    """P95 >> 1000ms → score 0."""
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
    responses = _fast_responses(15, latency_ms=200.0) + _error_responses(5)
    adapter = await _mock_adapter(responses)
    result = await check_latency_p95(adapter)
    assert result.passed is True
    assert "excluded from P95" in result.detail


@pytest.mark.asyncio
async def test_insufficient_sample_border():
    """9 successes out of 20 → below minimum 10 → score 0."""
    responses = _fast_responses(9, latency_ms=200.0) + _error_responses(11)
    adapter = await _mock_adapter(responses)
    result = await check_latency_p95(adapter)
    assert result.passed is False
    assert result.score == 0


@pytest.mark.asyncio
async def test_detail_contains_threshold():
    """Detail string always mentions the pass threshold."""
    adapter = await _mock_adapter(_fast_responses(20, latency_ms=300.0))
    result = await check_latency_p95(adapter)
    assert "1000" in result.detail


# ---------------------------------------------------------------------------
# Score function unit tests — exhaustive band coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p95_ms,expected_score", [
    (0.0,    100),   # perfect
    (200.0,  100),   # at ≤200 boundary
    (200.1,   80),   # just above 200
    (500.0,   80),   # at ≤500 boundary
    (500.1,   60),   # just above 500
    (1000.0,  60),   # at ≤1000 boundary (pass threshold)
    (1000.1,   0),   # just above threshold → fail
    (2000.0,   0),
    (9999.0,   0),
])
def test_score_function_bands(p95_ms: float, expected_score: int):
    assert _score_from_p95(p95_ms) == expected_score
