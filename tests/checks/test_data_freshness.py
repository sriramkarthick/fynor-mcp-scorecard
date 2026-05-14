"""
tests/checks/test_data_freshness.py — Unit tests for check_data_freshness.

No network required — adapter.call() is mocked.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from fynor.adapters.base import Response
from fynor.checks.mcp.data_freshness import check_data_freshness, _score_from_age_minutes


def _response_with_timestamp(age_minutes: float, field: str = "timestamp") -> Response:
    ts = datetime.now(tz=timezone.utc) - timedelta(minutes=age_minutes)
    return Response(
        status_code=200,
        body={"data": "test", field: ts.isoformat()},
        latency_ms=50.0,
    )


async def _mock_adapter(response: Response):
    adapter = AsyncMock()
    adapter.call = AsyncMock(return_value=response)
    return adapter


@pytest.mark.asyncio
async def test_fresh_data_scores_100():
    adapter = await _mock_adapter(_response_with_timestamp(1.0))
    result = await check_data_freshness(adapter)
    assert result.score == 100
    assert result.passed is True
    assert result.value is not None and result.value <= 5.0


@pytest.mark.asyncio
async def test_within_60min_scores_80():
    adapter = await _mock_adapter(_response_with_timestamp(30.0))
    result = await check_data_freshness(adapter)
    assert result.score == 80
    assert result.passed is True


@pytest.mark.asyncio
async def test_within_24h_scores_60_and_passes():
    adapter = await _mock_adapter(_response_with_timestamp(12 * 60))
    result = await check_data_freshness(adapter)
    assert result.score == 60
    assert result.passed is True


@pytest.mark.asyncio
async def test_stale_data_scores_20_and_fails():
    adapter = await _mock_adapter(_response_with_timestamp(25 * 60))
    result = await check_data_freshness(adapter)
    assert result.score == 20
    assert result.passed is False


@pytest.mark.asyncio
async def test_no_timestamp_scores_0():
    response = Response(status_code=200, body={"data": "no-ts"}, latency_ms=50.0)
    adapter = await _mock_adapter(response)
    result = await check_data_freshness(adapter)
    assert result.score == 0
    assert result.passed is False
    assert result.value is None


@pytest.mark.asyncio
async def test_empty_body_scores_0():
    response = Response(status_code=200, body=None, latency_ms=50.0)
    adapter = await _mock_adapter(response)
    result = await check_data_freshness(adapter)
    assert result.score == 0
    assert result.passed is False


@pytest.mark.asyncio
async def test_updated_at_field_detected():
    adapter = await _mock_adapter(_response_with_timestamp(2.0, field="updated_at"))
    result = await check_data_freshness(adapter)
    assert result.score == 100
    assert "updated_at" in result.detail


@pytest.mark.asyncio
async def test_nested_timestamp_detected():
    ts = (datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat()
    response = Response(
        status_code=200,
        body={"meta": {"timestamp": ts}, "data": []},
        latency_ms=50.0,
    )
    adapter = AsyncMock()
    adapter.call = AsyncMock(return_value=response)
    result = await check_data_freshness(adapter)
    assert result.score == 100


@pytest.mark.asyncio
async def test_probe_exception_scores_0():
    adapter = AsyncMock()
    adapter.call = AsyncMock(side_effect=Exception("connection refused"))
    result = await check_data_freshness(adapter)
    assert result.score == 0
    assert result.passed is False


@pytest.mark.asyncio
async def test_epoch_timestamp_accepted():
    """Unix epoch timestamps (numeric) should be accepted."""
    import time
    epoch_ts = time.time() - 60  # 1 minute ago
    response = Response(
        status_code=200,
        body={"ts": epoch_ts},
        latency_ms=50.0,
    )
    adapter = AsyncMock()
    adapter.call = AsyncMock(return_value=response)
    result = await check_data_freshness(adapter)
    assert result.score == 100


@pytest.mark.parametrize("age_min,expected", [
    (0.0, 100),
    (4.9, 100),
    (5.0, 100),
    (5.1, 80),
    (59.9, 80),
    (60.0, 80),
    (60.1, 60),
    (23 * 60, 60),
    (24 * 60, 60),
    (24 * 60 + 1, 20),
    (7 * 24 * 60, 20),
])
def test_score_function_bands(age_min, expected):
    assert _score_from_age_minutes(age_min) == expected
