"""
tests/checks/test_retry.py — Unit tests for check_retry.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from fynor.adapters.base import Response
from fynor.checks.mcp.retry import check_retry


def _adapter_with_responses(r1: Response, r2: Response) -> AsyncMock:
    """Return adapter that gives r1 for first call, r2 for second."""
    adapter = AsyncMock()
    adapter.call = AsyncMock(side_effect=[r1, r2])
    return adapter


@pytest.mark.asyncio
async def test_correct_400_scores_100():
    """Both probes return 400 with JSON-RPC error → score 100."""
    good = Response(
        status_code=400,
        body={"jsonrpc": "2.0", "error": {"code": -32600, "message": "bad"}},
        latency_ms=20.0,
    )
    adapter = _adapter_with_responses(good, good)
    result = await check_retry(adapter)
    assert result.passed is True
    assert result.score == 100


@pytest.mark.asyncio
async def test_400_plain_text_scores_80():
    """Both probes return 400 with plain text → score 80 → passes."""
    r = Response(status_code=400, body="Bad Request", latency_ms=20.0)
    adapter = _adapter_with_responses(r, r)
    result = await check_retry(adapter)
    assert result.passed is True
    assert result.score == 80


@pytest.mark.asyncio
async def test_200_with_error_object_scores_60():
    """Both probes return 200 with JSON-RPC error → score 60 → passes."""
    r = Response(
        status_code=200,
        body={"jsonrpc": "2.0", "id": 1, "error": {"code": -32600}},
        latency_ms=20.0,
    )
    adapter = _adapter_with_responses(r, r)
    result = await check_retry(adapter)
    assert result.passed is True
    assert result.score == 60


@pytest.mark.asyncio
async def test_5xx_crash_scores_0():
    """Both probes return 500 → score 0 → fails."""
    r = Response(status_code=500, body="Server Error", latency_ms=100.0)
    adapter = _adapter_with_responses(r, r)
    result = await check_retry(adapter)
    assert result.passed is False
    assert result.score == 0


@pytest.mark.asyncio
async def test_silent_success_scores_20():
    """Both probes return 200 with no error field → score 20 → fails."""
    r = Response(status_code=200, body={"result": "ok"}, latency_ms=50.0)
    adapter = _adapter_with_responses(r, r)
    result = await check_retry(adapter)
    assert result.passed is False
    assert result.score == 20


@pytest.mark.asyncio
async def test_connection_error_scores_0():
    """Connection error → score 0 → fails."""
    r = Response(status_code=0, body=None, latency_ms=5000.0, error="timeout after 10s")
    adapter = _adapter_with_responses(r, r)
    result = await check_retry(adapter)
    assert result.passed is False
    assert result.score == 0


@pytest.mark.asyncio
async def test_mixed_scores_averaged():
    """One 400 (score 100) and one 500 (score 0) → average 50 → fails."""
    r_good = Response(
        status_code=400,
        body={"error": {"code": -32600}},
        latency_ms=20.0,
    )
    r_bad = Response(status_code=500, body="Error", latency_ms=100.0)
    adapter = _adapter_with_responses(r_good, r_bad)
    result = await check_retry(adapter)
    assert result.score == 50
    assert result.passed is False   # avg 50 < 60 threshold
