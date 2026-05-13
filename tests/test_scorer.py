"""
tests/test_scorer.py — Unit tests for the scoring engine.

Tests the weighted grade calculation and the ADR-02 security cap.
No network calls — all inputs are synthetic CheckResult objects.
"""

from fynor.history import CheckResult
from fynor.scorer import score


def _make_result(check: str, passed: bool, sc: int) -> CheckResult:
    return CheckResult(check=check, passed=passed, score=sc, detail="test")


def test_all_passing_grades_a():
    results = [
        _make_result("latency_p95",       True, 100),
        _make_result("error_rate",         True, 100),
        _make_result("schema",             True, 100),
        _make_result("retry",              True, 100),
        _make_result("auth_token",         True, 100),
        _make_result("rate_limit",         True, 100),
        _make_result("timeout",            True, 100),
        _make_result("log_completeness",   True, 100),
    ]
    sc = score("https://example.com", "mcp", results)
    assert sc.grade == "A"
    assert sc.weighted_score == 100.0
    assert not sc.security_capped


def test_adr02_security_cap_limits_to_d():
    """A zero auth_token score must cap the grade at D even if all other checks pass."""
    results = [
        _make_result("latency_p95",       True,  100),
        _make_result("error_rate",         True,  100),
        _make_result("schema",             True,  100),
        _make_result("retry",              True,  100),
        _make_result("auth_token",         False,   0),   # critical failure
        _make_result("rate_limit",         True,  100),
        _make_result("timeout",            True,  100),
        _make_result("log_completeness",   True,  100),
    ]
    sc = score("https://example.com", "mcp", results)
    assert sc.grade in ("D", "F")
    assert sc.security_capped is True
    assert sc.weighted_score <= 59.0


def test_all_failing_grades_f():
    results = [
        _make_result(check, False, 0)
        for check in [
            "latency_p95", "error_rate", "schema", "retry",
            "auth_token", "rate_limit", "timeout", "log_completeness",
        ]
    ]
    sc = score("https://example.com", "mcp", results)
    assert sc.grade == "F"
    assert sc.weighted_score == 0.0


def test_grade_b_range():
    results = [
        _make_result("latency_p95",       True,  80),
        _make_result("error_rate",         True,  80),
        _make_result("schema",             True,  80),
        _make_result("retry",              True,  80),
        _make_result("auth_token",         True,  80),
        _make_result("rate_limit",         True,  80),
        _make_result("timeout",            True,  80),
        _make_result("log_completeness",   True,  80),
    ]
    sc = score("https://example.com", "mcp", results)
    assert sc.grade == "B"


def test_summary_lists_failed_checks():
    results = [
        _make_result("latency_p95",  False,  0),
        _make_result("auth_token",   True, 100),
    ]
    sc = score("https://example.com", "mcp", results)
    assert "latency_p95" in sc.summary
