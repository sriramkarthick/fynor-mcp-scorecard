"""
tests/checks/test_schema.py — Unit tests for check_schema.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from fynor.adapters.base import Response
from fynor.checks.mcp.schema import check_schema, _validate_envelope


def _adapter_for(body) -> AsyncMock:
    adapter = AsyncMock()
    adapter.call = AsyncMock(return_value=Response(status_code=200, body=body, latency_ms=10.0))
    return adapter


@pytest.mark.asyncio
async def test_valid_envelope_scores_100():
    """Valid JSON-RPC 2.0 response → score 100."""
    body = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.passed is True
    assert result.score == 100
    assert result.check == "schema"


@pytest.mark.asyncio
async def test_valid_error_envelope_scores_100():
    """JSON-RPC error object is still a valid envelope."""
    body = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "Invalid request"}}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.passed is True
    assert result.score == 100


@pytest.mark.asyncio
async def test_non_json_body_scores_0():
    """Non-JSON response → score 0."""
    adapter = _adapter_for("plain text response")
    result = await check_schema(adapter)
    assert result.passed is False
    assert result.score == 0
    assert "not JSON" in result.detail


@pytest.mark.asyncio
async def test_missing_jsonrpc_field_scores_60():
    """Missing jsonrpc field → 1 issue → score 60 (pass)."""
    body = {"id": 1, "result": {}}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.score == 60
    assert result.passed is True


@pytest.mark.asyncio
async def test_wrong_jsonrpc_version_scores_60():
    """jsonrpc != '2.0' → 1 issue → score 60."""
    body = {"jsonrpc": "1.0", "id": 1, "result": {}}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.score == 60
    assert result.passed is True


@pytest.mark.asyncio
async def test_missing_id_field_scores_60():
    """Missing id field → 1 issue → score 60."""
    body = {"jsonrpc": "2.0", "result": {}}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.score == 60


@pytest.mark.asyncio
async def test_both_result_and_error_scores_60():
    """Both result and error present → 1 issue (mutually exclusive) → score 60."""
    body = {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.score == 60


@pytest.mark.asyncio
async def test_neither_result_nor_error_scores_60():
    """Neither result nor error → 1 issue → score 60."""
    body = {"jsonrpc": "2.0", "id": 1}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.score == 60


@pytest.mark.asyncio
async def test_multiple_issues_scores_0():
    """Multiple issues → score 0, fails."""
    # Missing jsonrpc + missing id + neither result nor error = 3 issues
    body = {}
    adapter = _adapter_for(body)
    result = await check_schema(adapter)
    assert result.passed is False
    assert result.score == 0


# ---------------------------------------------------------------------------
# Envelope validator unit tests
# ---------------------------------------------------------------------------

def test_validate_envelope_clean():
    body = {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert _validate_envelope(body) == []


def test_validate_envelope_wrong_version():
    body = {"jsonrpc": "1.0", "id": 1, "result": {}}
    issues = _validate_envelope(body)
    assert len(issues) == 1
    assert "2.0" in issues[0]


def test_validate_envelope_both_result_and_error():
    body = {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}}
    issues = _validate_envelope(body)
    assert len(issues) == 1
    assert "mutually exclusive" in issues[0].lower()
