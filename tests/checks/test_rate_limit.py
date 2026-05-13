"""
tests/checks/test_rate_limit.py — Unit tests for check_rate_limit.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from fynor.adapters.base import Response
from fynor.checks.mcp.rate_limit import check_rate_limit


def _burst_responses(
    n_ok: int,
    n_429: int = 0,
    n_5xx: int = 0,
    retry_after: bool = False,
) -> list[Response]:
    """Build a 50-response list with controlled mix."""
    responses: list[Response] = []
    responses += [Response(status_code=200, body={}, latency_ms=10.0) for _ in range(n_ok)]
    rl_headers = {"retry-after": "60"} if retry_after else {}
    responses += [
        Response(status_code=429, body=None, latency_ms=10.0, headers=rl_headers)
        for _ in range(n_429)
    ]
    responses += [Response(status_code=500, body=None, latency_ms=10.0) for _ in range(n_5xx)]
    assert len(responses) == 50, f"Expected 50, got {len(responses)}"
    return responses


async def _adapter(responses: list[Response]) -> AsyncMock:
    a = AsyncMock()
    a.burst = AsyncMock(return_value=responses)
    return a


@pytest.mark.asyncio
async def test_429_with_retry_after_scores_100():
    """429 + Retry-After header → score 100, passed."""
    adapter = await _adapter(_burst_responses(40, n_429=10, retry_after=True))
    result = await check_rate_limit(adapter)
    assert result.passed is True
    assert result.score == 100
    assert result.check == "rate_limit"


@pytest.mark.asyncio
async def test_429_without_retry_after_scores_60():
    """429 without Retry-After → score 60, passed."""
    adapter = await _adapter(_burst_responses(40, n_429=10, retry_after=False))
    result = await check_rate_limit(adapter)
    assert result.passed is True
    assert result.score == 60
    assert "Retry-After" in result.detail


@pytest.mark.asyncio
async def test_no_429_scores_30():
    """No 429 in burst → score 30, failed."""
    adapter = await _adapter(_burst_responses(50))
    result = await check_rate_limit(adapter)
    assert result.passed is False
    assert result.score == 30


@pytest.mark.asyncio
async def test_5xx_without_429_scores_0():
    """5xx errors with no 429 → server crashes instead of rate-limiting → score 0."""
    adapter = await _adapter(_burst_responses(40, n_5xx=10))
    result = await check_rate_limit(adapter)
    assert result.passed is False
    assert result.score == 0


@pytest.mark.asyncio
async def test_5xx_and_429_scores_100():
    """5xx AND 429 (rate limiting before crash) → 429 takes precedence, score 100."""
    adapter = await _adapter(_burst_responses(35, n_429=10, n_5xx=5, retry_after=True))
    result = await check_rate_limit(adapter)
    assert result.passed is True
    assert result.score == 100


@pytest.mark.asyncio
async def test_detail_includes_first_429_position():
    """Detail should mention which request number triggered the first 429."""
    # First 45 OK, then 5 rate-limited
    adapter = await _adapter(_burst_responses(45, n_429=5, retry_after=True))
    result = await check_rate_limit(adapter)
    assert result.passed is True
    assert "#46" in result.detail or "46" in result.detail


@pytest.mark.asyncio
async def test_value_is_429_count():
    """result.value is the count of 429 responses."""
    adapter = await _adapter(_burst_responses(40, n_429=10, retry_after=True))
    result = await check_rate_limit(adapter)
    assert result.value == 10
