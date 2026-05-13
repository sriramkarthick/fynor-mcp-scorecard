"""
tests/checks/test_log_completeness.py — Unit tests for check_log_completeness.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fynor.adapters.base import BaseAdapter, Response
from fynor.checks.mcp.log_completeness import (
    check_log_completeness,
    _score_log_body,
    _extract_keys,
)


def _base_adapter(target: str = "https://api.example.com/mcp") -> AsyncMock:
    adapter = AsyncMock(spec=BaseAdapter)
    adapter.target = target
    return adapter


# ---------------------------------------------------------------------------
# Tests using patched _probe_paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_json_with_timestamps_scores_100():
    """Structured JSON + timestamp → score 100, passed."""
    body = {"timestamp": "2026-01-01T00:00:00Z", "level": "INFO", "message": "ok"}
    adapter = _base_adapter()
    with patch("fynor.checks.mcp.log_completeness._probe_paths") as mock_probe:
        mock_probe.side_effect = [("/logs", body), None]  # log path hit, health not needed
        result = await check_log_completeness(adapter)

    assert result.passed is True
    assert result.score == 100
    assert result.check == "log_completeness"
    assert result.value == "/logs"


@pytest.mark.asyncio
async def test_json_without_timestamps_scores_70():
    """Structured JSON but no timestamp fields → score 70, passed."""
    body = {"level": "INFO", "message": "started"}
    adapter = _base_adapter()
    with patch("fynor.checks.mcp.log_completeness._probe_paths") as mock_probe:
        mock_probe.side_effect = [("/logs", body), None]
        result = await check_log_completeness(adapter)

    assert result.passed is True
    assert result.score == 70


@pytest.mark.asyncio
async def test_plain_text_logs_score_60():
    """Plain text log endpoint → score 60, passed (log exists)."""
    adapter = _base_adapter()
    with patch("fynor.checks.mcp.log_completeness._probe_paths") as mock_probe:
        mock_probe.side_effect = [("/logs", "INFO 2026-01-01 Server started"), None]
        result = await check_log_completeness(adapter)

    assert result.passed is True
    assert result.score == 60
    assert "Plain-text" in result.detail


@pytest.mark.asyncio
async def test_health_only_scores_40():
    """Only health endpoint found → score 40, failed (not an audit log)."""
    adapter = _base_adapter()
    with patch("fynor.checks.mcp.log_completeness._probe_paths") as mock_probe:
        # First call (log paths) returns None, second call (health paths) finds /health
        mock_probe.side_effect = [None, ("/health", {"status": "ok"})]
        result = await check_log_completeness(adapter)

    assert result.passed is False
    assert result.score == 40
    assert "/health" in result.detail


@pytest.mark.asyncio
async def test_no_endpoint_found_scores_0():
    """No observability endpoints found → score 0, failed."""
    adapter = _base_adapter()
    with patch("fynor.checks.mcp.log_completeness._probe_paths") as mock_probe:
        mock_probe.return_value = None
        result = await check_log_completeness(adapter)

    assert result.passed is False
    assert result.score == 0
    assert "No observability endpoint" in result.detail


@pytest.mark.asyncio
async def test_list_of_log_entries_with_ts():
    """Log endpoint returns a list of entries with 'ts' field → score 100."""
    body = [
        {"ts": "2026-01-01T00:00:00Z", "msg": "startup"},
        {"ts": "2026-01-01T00:00:01Z", "msg": "ready"},
    ]
    adapter = _base_adapter()
    with patch("fynor.checks.mcp.log_completeness._probe_paths") as mock_probe:
        mock_probe.side_effect = [("/audit", body), None]
        result = await check_log_completeness(adapter)

    assert result.passed is True
    assert result.score == 100


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------

def test_score_log_body_json_with_timestamps():
    result = _score_log_body("/logs", {"timestamp": "...", "level": "INFO"})
    assert result.score == 100
    assert result.passed is True


def test_score_log_body_json_without_timestamps():
    result = _score_log_body("/logs", {"level": "INFO", "msg": "hello"})
    assert result.score == 70
    assert result.passed is True


def test_score_log_body_plain_text():
    result = _score_log_body("/logs", "plain text log content")
    assert result.score == 60
    assert result.passed is True


def test_extract_keys_dict():
    body = {"Timestamp": "...", "LEVEL": "INFO"}
    keys = _extract_keys(body)
    assert "timestamp" in keys
    assert "level" in keys


def test_extract_keys_nested():
    body = {"meta": {"created_at": "2026-01-01"}}
    keys = _extract_keys(body)
    assert "created_at" in keys


def test_extract_keys_list():
    body = [{"ts": "...", "msg": "a"}, {"ts": "...", "msg": "b"}]
    keys = _extract_keys(body)
    assert "ts" in keys
