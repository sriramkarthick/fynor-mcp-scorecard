"""
tests/test_profiles.py — Unit tests for fynor/profiles.py.

Tests profile loading, apply_profile threshold overrides, and the critical
regression that apply_profile must preserve result="na" on N/A checks.
No network calls — all inputs are synthetic CheckResult objects.
"""

import pytest

from fynor.history import CheckResult
from fynor.profiles import (
    DEFAULT_PROFILE,
    FINANCIAL_PROFILE,
    SECURITY_PROFILE,
    CheckProfile,
    apply_profile,
    get_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make(check: str, passed: bool, score: int, result: str = "") -> CheckResult:
    return CheckResult(check=check, passed=passed, score=score, detail="test", result=result)


def _make_na(check: str) -> CheckResult:
    """Simulate an N/A check as produced by cli.py for non-MCP targets."""
    return CheckResult(
        check=check,
        passed=False,
        score=0,
        value=None,
        detail="Not applicable: this check only applies to MCP (JSON-RPC 2.0) interfaces.",
        result="na",
    )


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------

class TestGetProfile:
    def test_returns_default(self) -> None:
        p = get_profile("default")
        assert p.name == "default"

    def test_returns_security(self) -> None:
        p = get_profile("security")
        assert p.name == "security"

    def test_returns_financial(self) -> None:
        p = get_profile("financial")
        assert p.name == "financial"

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown profile"):
            get_profile("nonexistent")


# ---------------------------------------------------------------------------
# apply_profile — default profile (no thresholds — pass through unchanged)
# ---------------------------------------------------------------------------

class TestApplyProfileDefault:
    def test_default_returns_same_list(self) -> None:
        results = [_make("latency_p95", True, 100), _make("error_rate", True, 100)]
        out = apply_profile(results, DEFAULT_PROFILE)
        assert out is results  # identity: no-op when pass_thresholds is empty

    def test_default_preserves_na(self) -> None:
        results = [_make_na("schema"), _make("latency_p95", True, 100)]
        out = apply_profile(results, DEFAULT_PROFILE)
        # Default profile has no thresholds — returns identical list
        assert out[0].result == "na"


# ---------------------------------------------------------------------------
# apply_profile — security profile threshold overrides
# ---------------------------------------------------------------------------

class TestApplyProfileSecurity:
    def test_raises_threshold_fails_check(self) -> None:
        # error_rate threshold = 90; score 80 should now be a FAIL
        results = [_make("error_rate", True, 80)]  # originally passed at default
        out = apply_profile(results, SECURITY_PROFILE)
        assert not out[0].passed

    def test_raises_threshold_keeps_pass(self) -> None:
        # error_rate threshold = 90; score 95 still passes
        results = [_make("error_rate", True, 95)]
        out = apply_profile(results, SECURITY_PROFILE)
        assert out[0].passed

    def test_untouched_check_unchanged(self) -> None:
        # auth_token not in security profile thresholds — kept as-is
        results = [_make("auth_token", False, 0)]
        out = apply_profile(results, SECURITY_PROFILE)
        assert not out[0].passed
        assert out[0].score == 0

    # -----------------------------------------------------------------
    # REGRESSION: apply_profile must NOT drop result="na"
    # Bug: CheckResult was rebuilt without result=r.result, so N/A checks
    # silently became result="" and re-entered scoring as failures.
    # -----------------------------------------------------------------

    def test_na_check_result_preserved_when_threshold_exists(self) -> None:
        """
        tool_description_quality is in SECURITY_PROFILE.pass_thresholds (threshold=80).
        When this check is N/A for a REST target, apply_profile must keep result="na".
        Previously it dropped the field, causing the N/A check to score as 0 (FAIL).
        """
        results = [_make_na("tool_description_quality")]
        out = apply_profile(results, SECURITY_PROFILE)
        assert out[0].result == "na", (
            "apply_profile must preserve result='na' — "
            "N/A checks must not re-enter scoring after profiling"
        )

    def test_na_check_passed_field_not_inflated(self) -> None:
        """N/A check with score=0 must not be flipped to passed even under a threshold."""
        results = [_make_na("tool_description_quality")]
        out = apply_profile(results, SECURITY_PROFILE)
        # score=0 < threshold=80, so passed should be False
        assert not out[0].passed

    def test_na_preserves_detail_and_value(self) -> None:
        """All original fields survive a profile application on an N/A result."""
        na = _make_na("schema")
        results = [na]
        # schema is not in SECURITY_PROFILE.pass_thresholds, so result is kept as-is
        out = apply_profile(results, SECURITY_PROFILE)
        assert out[0].detail == na.detail
        assert out[0].value is None

    def test_multiple_na_checks_all_preserved(self) -> None:
        """Batch: all three MCP-only N/A checks keep result='na' after security profile."""
        na_checks = [_make_na(c) for c in ("schema", "retry", "tool_description_quality")]
        out = apply_profile(na_checks, SECURITY_PROFILE)
        for r in out:
            assert r.result == "na", f"check={r.check} lost result='na' after profiling"


# ---------------------------------------------------------------------------
# apply_profile — financial profile
# ---------------------------------------------------------------------------

class TestApplyProfileFinancial:
    def test_log_completeness_threshold_applied(self) -> None:
        # financial requires score=100; score=60 should fail
        results = [_make("log_completeness", True, 60)]
        out = apply_profile(results, FINANCIAL_PROFILE)
        assert not out[0].passed

    def test_schema_na_preserved_under_financial(self) -> None:
        """schema is in FINANCIAL_PROFILE.pass_thresholds (threshold=100).
        If schema is N/A (non-MCP target), result='na' must survive."""
        results = [_make_na("schema")]
        out = apply_profile(results, FINANCIAL_PROFILE)
        assert out[0].result == "na"


# ---------------------------------------------------------------------------
# CheckProfile dataclass
# ---------------------------------------------------------------------------

class TestCheckProfileDataclass:
    def test_frozen(self) -> None:
        p = CheckProfile(name="test", description="test", pass_thresholds={"x": 80})
        with pytest.raises((AttributeError, TypeError)):
            p.name = "changed"  # type: ignore[misc]

    def test_default_thresholds_empty(self) -> None:
        p = CheckProfile(name="bare", description="bare")
        assert p.pass_thresholds == {}
