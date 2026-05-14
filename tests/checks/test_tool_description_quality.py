"""
tests/checks/test_tool_description_quality.py — Unit tests for check_tool_description_quality.

No network required — adapter.call() is mocked.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from fynor.adapters.base import Response
from fynor.checks.mcp.tool_description_quality import check_tool_description_quality


def _tool(name: str, desc: str = "", schema: dict | None = None) -> dict:
    t: dict = {"name": name, "description": desc}
    if schema is not None:
        t["inputSchema"] = schema
    return t


def _full_schema() -> dict:
    return {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}


def _tools_response(tools: list) -> Response:
    return Response(
        status_code=200,
        body={"jsonrpc": "2.0", "id": 1, "result": {"tools": tools}},
        latency_ms=50.0,
    )


async def _mock_adapter(response: Response):
    adapter = AsyncMock()
    adapter.call = AsyncMock(return_value=response)
    return adapter


@pytest.mark.asyncio
async def test_fully_described_tools_score_100():
    tools = [_tool("search", "A" * 60, _full_schema())]
    adapter = await _mock_adapter(_tools_response(tools))
    result = await check_tool_description_quality(adapter)
    assert result.score == 100
    assert result.passed is True
    assert result.value == 1


@pytest.mark.asyncio
async def test_adequate_tools_score_80():
    tools = [_tool("search", "A" * 25, {"type": "object"})]
    adapter = await _mock_adapter(_tools_response(tools))
    result = await check_tool_description_quality(adapter)
    assert result.score == 80
    assert result.passed is True


@pytest.mark.asyncio
async def test_description_only_scores_60():
    tools = [_tool("search", "A" * 15)]
    adapter = await _mock_adapter(_tools_response(tools))
    result = await check_tool_description_quality(adapter)
    assert result.score == 60
    assert result.passed is True


@pytest.mark.asyncio
async def test_short_description_scores_20():
    tools = [_tool("x", "bad")]
    adapter = await _mock_adapter(_tools_response(tools))
    result = await check_tool_description_quality(adapter)
    assert result.score == 20
    assert result.passed is False


@pytest.mark.asyncio
async def test_missing_description_scores_20():
    tools = [{"name": "search"}]
    adapter = await _mock_adapter(_tools_response(tools))
    result = await check_tool_description_quality(adapter)
    assert result.score == 20
    assert result.passed is False


@pytest.mark.asyncio
async def test_empty_tools_list_scores_0():
    adapter = await _mock_adapter(_tools_response([]))
    result = await check_tool_description_quality(adapter)
    assert result.score == 0
    assert result.passed is False


@pytest.mark.asyncio
async def test_worst_case_wins():
    """One bad tool drags down a list of good ones."""
    tools = [
        _tool("good", "A" * 60, _full_schema()),
        _tool("bad", "x"),
    ]
    adapter = await _mock_adapter(_tools_response(tools))
    result = await check_tool_description_quality(adapter)
    assert result.score == 20
    assert result.passed is False
    assert result.value == 1  # only 1 fully described


@pytest.mark.asyncio
async def test_call_failure_scores_0():
    adapter = AsyncMock()
    adapter.call = AsyncMock(side_effect=Exception("timeout"))
    result = await check_tool_description_quality(adapter)
    assert result.score == 0
    assert result.passed is False


@pytest.mark.asyncio
async def test_detail_lists_inadequate_tools():
    """Detail string identifies which tools are inadequate."""
    tools = [_tool("weak_tool", "short")]
    adapter = await _mock_adapter(_tools_response(tools))
    result = await check_tool_description_quality(adapter)
    assert "weak_tool" in result.detail
