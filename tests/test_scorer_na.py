"""
tests/test_scorer_na.py — Scorer behaviour when checks return result="na".

T11b: tests written FIRST (decision D8 — test-first locked) before
implementing _redistribute_weights() in scorer.py.

The na contract:
  - Checks with result="na" are excluded from category averaging.
  - When a category has zero scored (non-na) checks, its weight is
    distributed equally to the non-empty categories.
  - Security cap (auth_token score 0 → max grade D) fires AFTER
    weight redistribution.
  - A run where all checks are na produces grade "N/A", score 0.0,
    security_capped=False.
"""

from __future__ import annotations

import pytest

from fynor.history import CheckResult
from fynor.scorer import score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(check: str, sc: int, *, na: bool = False) -> CheckResult:
    """Build a CheckResult. na=True sets result='na' and passed=True (not a failure)."""
    if na:
        return CheckResult(check=check, passed=True, score=0, result="na",
                          detail="not applicable for this interface type")
    return CheckResult(check=check, passed=sc >= 60, score=sc,
                      result="pass" if sc >= 60 else "fail", detail="test")


# ---------------------------------------------------------------------------
# na checks are excluded from their category average
# ---------------------------------------------------------------------------

class TestNaExclusion:

    def test_na_check_not_dragged_into_average(self):
        """
        An na check must be excluded from its category.
        Here performance has latency_p95=100 and rate_limit=na.
        Performance avg should be 100 (not 50 if na were scored as 0).
        """
        results = [
            _r("auth_token",       100),
            _r("error_rate",       100),
            _r("schema",           100),
            _r("retry",            100),
            _r("timeout",          100),
            _r("log_completeness", 100),
            _r("latency_p95",      100),   # performance: 100
            _r("rate_limit",         0, na=True),  # na — must not score
        ]
        sc = score("https://example.com", "graphql", results)
        assert sc.performance_score == 100.0
        assert sc.grade == "A"
        assert sc.weighted_score == 100.0

    def test_na_check_in_reliability_excluded(self):
        """
        Reliability has 6 checks; one returns na.
        Average should be computed over 5 non-na checks only.
        """
        results = [
            _r("auth_token",       100),
            _r("latency_p95",      100),
            _r("rate_limit",       100),
            _r("error_rate",       100),
            _r("schema",           100),
            _r("retry",            100),
            _r("timeout",          100),
            _r("log_completeness",   0, na=True),  # na — excluded
        ]
        sc = score("https://example.com", "graphql", results)
        assert sc.reliability_score == 100.0


# ---------------------------------------------------------------------------
# Weight redistribution — empty category gets its weight pushed to others
# ---------------------------------------------------------------------------

class TestWeightRedistribution:

    def test_performance_bucket_empty_weight_goes_to_security_and_reliability(self):
        """
        When the entire performance bucket is na, its 30% weight is
        distributed equally to security (30%) and reliability (40%).
        New weights: security = 30 + 15 = 45%, reliability = 40 + 15 = 55%.
        With all non-na checks at 100, weighted_score should still be 100.
        """
        results = [
            _r("auth_token",       100),
            _r("error_rate",       100),
            _r("schema",           100),
            _r("retry",            100),
            _r("timeout",          100),
            _r("log_completeness", 100),
            _r("latency_p95",        0, na=True),  # performance na
            _r("rate_limit",         0, na=True),  # performance na
        ]
        sc = score("https://example.com", "websocket", results)
        assert sc.performance_score == 0.0   # no scored checks → 0 average (or sentinel)
        assert sc.weighted_score == 100.0    # all scored checks are 100
        assert sc.grade == "A"

    def test_performance_empty_partial_scores_redistribute_correctly(self):
        """
        All performance checks na. Security=80, Reliability=60.
        Old weights (30/40/30): weighted = 0.3*80 + 0.4*60 + 0.3*100 = 24+24+30=78
        New weights (45/55): weighted = 0.45*80 + 0.55*60 = 36+33 = 69
        Grade should be C (60-74 band) under redistribution.
        """
        results = [
            _r("auth_token",       80),   # security
            _r("error_rate",       60),   # reliability
            _r("schema",           60),   # reliability
            _r("retry",            60),   # reliability
            _r("timeout",          60),   # reliability
            _r("log_completeness", 60),   # reliability
            _r("latency_p95",       0, na=True),
            _r("rate_limit",        0, na=True),
        ]
        sc = score("https://example.com", "websocket", results)
        # 0.45*80 + 0.55*60 = 36 + 33 = 69 → C
        assert sc.grade == "C"
        assert abs(sc.weighted_score - 69.0) < 1.0

    def test_security_weight_never_diluted(self):
        """
        Even if reliability is empty-na, security weight must never drop
        below 30%. Security is the floor weight by design (ADR-02).
        With only security and performance, weights become 50/50.
        """
        results = [
            _r("auth_token",       100),   # security
            _r("latency_p95",      100),   # performance
            _r("rate_limit",       100),   # performance
            # All reliability checks na:
            _r("error_rate",         0, na=True),
            _r("schema",             0, na=True),
            _r("retry",              0, na=True),
            _r("timeout",            0, na=True),
            _r("log_completeness",   0, na=True),
        ]
        sc = score("https://example.com", "grpc", results)
        assert sc.weighted_score == 100.0
        assert sc.grade == "A"


# ---------------------------------------------------------------------------
# Security cap fires AFTER redistribution
# ---------------------------------------------------------------------------

class TestSecurityCapAfterRedistribution:

    def test_security_cap_applies_after_weight_redistribution(self):
        """
        Performance bucket all-na → redistribution happens.
        Then auth_token=0 → cap kicks in. Grade must be ≤ D.
        """
        results = [
            _r("auth_token",         0),   # security: 0 → cap
            _r("error_rate",       100),
            _r("schema",           100),
            _r("retry",            100),
            _r("timeout",          100),
            _r("log_completeness", 100),
            _r("latency_p95",        0, na=True),
            _r("rate_limit",         0, na=True),
        ]
        sc = score("https://example.com", "websocket", results)
        assert sc.security_capped is True
        assert sc.weighted_score <= 59.0
        assert sc.grade in ("D", "F")

    def test_cap_does_not_fire_when_security_passes_after_redistribution(self):
        """Security passes (score > 0) even after redistribution → no cap."""
        results = [
            _r("auth_token",       100),
            _r("error_rate",        50),
            _r("schema",            50),
            _r("retry",             50),
            _r("timeout",           50),
            _r("log_completeness",  50),
            _r("latency_p95",        0, na=True),
            _r("rate_limit",         0, na=True),
        ]
        sc = score("https://example.com", "websocket", results)
        assert sc.security_capped is False


# ---------------------------------------------------------------------------
# All-na run
# ---------------------------------------------------------------------------

class TestAllNa:

    def test_all_na_returns_na_grade(self):
        """
        If every check returns na, grade is 'N/A', weighted_score is 0.0,
        and security_capped is False (there is no security failure).
        """
        results = [
            _r(check, 0, na=True)
            for check in [
                "latency_p95", "error_rate", "schema", "retry",
                "auth_token", "rate_limit", "timeout", "log_completeness",
            ]
        ]
        sc = score("https://example.com", "unknown", results)
        assert sc.grade == "N/A"
        assert sc.security_capped is False


# ---------------------------------------------------------------------------
# Backward compat: existing CheckResult without result field still scores
# ---------------------------------------------------------------------------

class TestBackwardCompat:

    def test_legacy_checkresult_no_result_field_still_scores(self):
        """
        CheckResults created without the result field (result="") must
        be treated as normal scored checks (not na).
        """
        results = [
            CheckResult(check="auth_token", passed=True, score=100, detail="test"),
            CheckResult(check="latency_p95", passed=True, score=100, detail="test"),
            CheckResult(check="error_rate", passed=True, score=100, detail="test"),
        ]
        sc = score("https://example.com", "mcp", results)
        # Should score normally — result="" is not "na"
        assert sc.security_score == 100.0
        assert sc.performance_score == 100.0
        assert sc.grade == "A"
