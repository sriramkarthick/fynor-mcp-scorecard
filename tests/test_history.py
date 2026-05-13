"""
tests/test_history.py — Unit tests for the history log.

Tests append, read, and filter operations.
Uses a temporary file so no real ~/.fynor/history.jsonl is touched.
"""

import tempfile
from pathlib import Path

from fynor.history import CheckResult, append_result, read_history


def _temp_path(tmp_dir: str) -> Path:
    return Path(tmp_dir) / "test_history.jsonl"


def test_append_and_read(tmp_path):
    path = tmp_path / "history.jsonl"
    result = CheckResult(check="latency_p95", passed=True, score=95, value=340.0, detail="ok")
    append_result("https://example.com", "mcp", result, path=path)

    rows = read_history(path=path)
    assert len(rows) == 1
    assert rows[0]["check"] == "latency_p95"
    assert rows[0]["target"] == "https://example.com"
    assert rows[0]["passed"] is True
    assert rows[0]["score"] == 95


def test_filter_by_target(tmp_path):
    path = tmp_path / "history.jsonl"
    r = CheckResult(check="latency_p95", passed=True, score=90, detail="ok")
    append_result("https://api-a.com", "mcp", r, path=path)
    append_result("https://api-b.com", "mcp", r, path=path)

    rows_a = read_history(target="https://api-a.com", path=path)
    assert len(rows_a) == 1
    assert rows_a[0]["target"] == "https://api-a.com"


def test_filter_by_check(tmp_path):
    path = tmp_path / "history.jsonl"
    append_result("https://api.com", "mcp",
                  CheckResult(check="latency_p95", passed=True, score=90, detail="ok"),
                  path=path)
    append_result("https://api.com", "mcp",
                  CheckResult(check="auth_token", passed=False, score=0, detail="fail"),
                  path=path)

    auth_rows = read_history(check="auth_token", path=path)
    assert len(auth_rows) == 1
    assert auth_rows[0]["check"] == "auth_token"


def test_multiple_appends_preserve_order(tmp_path):
    path = tmp_path / "history.jsonl"
    for i in range(5):
        append_result("https://api.com", "mcp",
                      CheckResult(check="latency_p95", passed=True, score=i * 10, detail="ok"),
                      path=path)

    rows = read_history(path=path)
    assert len(rows) == 5
    scores = [r["score"] for r in rows]
    assert scores == [0, 10, 20, 30, 40]


def test_empty_file_returns_empty_list(tmp_path):
    path = tmp_path / "nonexistent.jsonl"
    assert read_history(path=path) == []
