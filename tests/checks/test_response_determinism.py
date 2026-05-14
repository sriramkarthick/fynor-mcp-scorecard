"""
tests/checks/test_response_determinism.py — Unit tests for check_response_determinism.

No network required — adapter.call() is mocked.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from fynor.adapters.base import Response
from fynor.checks.mcp.response_determinism import check_response_determinism


def _response(body: dict) -> Response:
    return Response(status_code=200, body=body, latency_ms=50.0)


@pytest.mark.asyncio
async def test_identical_responses_score_100():
    body = {"jsonrpc": "2.0", "result": {"data": [1, 2, 3]}}
    adapter = AsyncMock()
    adapter.call = AsyncMock(return_value=_response(body))
    result = await check_response_determinism(adapter)
    assert result.score == 100
    assert result.passed is True
    assert result.value == 3


@pytest.mark.asyncio
async def test_two_of_three_agree_scores_60():
    bodies = [
        {"result": {"items": []}},
        {"result": {"items": []}},
        {"result": {"data": []}},
    ]
    adapter = AsyncMock()
    adapter.call = AsyncMock(side_effect=[_response(b) for b in bodies])
    result = await check_response_determinism(adapter)
    assert result.score == 60
    assert result.passed is True
    assert result.value == 2


@pytest.mark.asyncio
async def test_all_different_scores_0():
    bodies = [{"a": 1}, {"b": 2}, {"c": 3}]
    adapter = AsyncMock()
    adapter.call = AsyncMock(side_effect=[_response(b) for b in bodies])
    result = await check_response_determinism(adapter)
    assert result.score == 0
    assert result.passed is False


@pytest.mark.asyncio
async def test_probe_error_scores_0():
    adapter = AsyncMock()
    adapter.call = AsyncMock(side_effect=Exception("connection refused"))
    result = await check_response_determinism(adapter)
    assert result.score == 0
    assert result.passed is False
    assert "Probe failures" in result.detail


@pytest.mark.asyncio
async def test_value_changes_do_not_affect_score():
    """Same schema, different values → identical fingerprints → score 100."""
    bodies = [
        {"result": {"count": 10}},
        {"result": {"count": 20}},
        {"result": {"count": 30}},
    ]
    adapter = AsyncMock()
    adapter.call = AsyncMock(side_effect=[_response(b) for b in bodies])
    result = await check_response_determinism(adapter)
    assert result.score == 100
    assert result.passed is True


@pytest.mark.asyncio
async def test_empty_body_counts_as_error():
    response = Response(status_code=200, body=None, latency_ms=50.0)
    adapter = AsyncMock()
    adapter.call = AsyncMock(return_value=response)
    result = await check_response_determinism(adapter)
    assert result.score == 0
    assert result.passed is False
