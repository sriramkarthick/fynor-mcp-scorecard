"""
tests/test_interpretation.py — Unit tests for fynor/interpretation.py.

Verifies that every check in ALL_CHECKS has an interpretation for every
relevant score band, and that the interpret() function returns the correct
band given a CheckResult.

No network calls — all inputs are synthetic CheckResult objects.
"""

from __future__ import annotations

import pytest

from fynor.history import CheckResult
from fynor.interpretation import CheckInterpretation, interpret, interpret_all, _TABLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make(check: str, passed: bool, sc: int, result: str = "") -> CheckResult:
    return CheckResult(check=check, passed=passed, score=sc, detail="test", result=result)


def _make_na(check: str) -> CheckResult:
    return CheckResult(
        check=check, passed=False, score=0,
        detail="Not applicable.", result="na",
    )


# ---------------------------------------------------------------------------
# Band mapping correctness
# ---------------------------------------------------------------------------

class TestBandMapping:
    def test_score_100_maps_to_pass(self) -> None:
        r = _make("latency_p95", True, 100)
        interp = interpret(r)
        assert interp is not None
        # Pass interpretations have no remediation or reproduce steps needed
        assert "No action" in interp.remediation or interp.remediation == ""

    def test_score_60_maps_to_degraded(self) -> None:
        r = _make("latency_p95", True, 60)
        interp = interpret(r)
        assert interp is not None

    def test_score_90_maps_to_degraded(self) -> None:
        """Score 90 is a degraded band (passes threshold but not excellent)."""
        r = _make("error_rate", True, 90)
        interp = interpret(r)
        assert interp is not None

    def test_score_0_maps_to_fail(self) -> None:
        r = _make("auth_token", False, 0)
        interp = interpret(r)
        assert interp is not None

    def test_score_40_maps_to_fail(self) -> None:
        """Score 40 (auth partial failure) maps to fail band."""
        r = _make("auth_token", False, 40)
        interp = interpret(r)
        assert interp is not None

    def test_na_result_maps_to_na_band(self) -> None:
        r = _make_na("schema")
        interp = interpret(r)
        assert interp is not None
        assert "Not applicable" in interp.impact

    def test_unknown_check_returns_none(self) -> None:
        r = _make("nonexistent_check", False, 0)
        interp = interpret(r)
        assert interp is None


# ---------------------------------------------------------------------------
# Coverage: every registered check has fail and pass interpretations
# ---------------------------------------------------------------------------

# Checks that have N/A interpretations (MCP-only checks)
_MCP_ONLY_CHECKS = {"schema", "retry", "tool_description_quality"}

# All checks we expect to be covered
_ALL_CHECKS = {
    "latency_p95", "error_rate", "schema", "retry", "auth_token",
    "rate_limit", "timeout", "log_completeness", "data_freshness",
    "tool_description_quality", "response_determinism",
}


class TestTableCoverage:
    @pytest.mark.parametrize("check_name", sorted(_ALL_CHECKS))
    def test_every_check_has_fail_interpretation(self, check_name: str) -> None:
        assert (check_name, "fail") in _TABLE, (
            f"Missing fail interpretation for check '{check_name}'. "
            f"Add it to _TABLE in fynor/interpretation.py."
        )

    @pytest.mark.parametrize("check_name", sorted(_ALL_CHECKS))
    def test_every_check_has_pass_interpretation(self, check_name: str) -> None:
        assert (check_name, "pass") in _TABLE, (
            f"Missing pass interpretation for check '{check_name}'. "
            f"Add it to _TABLE in fynor/interpretation.py."
        )

    @pytest.mark.parametrize("check_name", sorted(_MCP_ONLY_CHECKS))
    def test_mcp_only_checks_have_na_interpretation(self, check_name: str) -> None:
        assert (check_name, "na") in _TABLE, (
            f"Missing na interpretation for MCP-only check '{check_name}'."
        )


# ---------------------------------------------------------------------------
# Content validation: interpretations must be non-empty and actionable
# ---------------------------------------------------------------------------

class TestInterpretationContent:
    @pytest.mark.parametrize("key", list(_TABLE.keys()))
    def test_impact_is_non_empty(self, key: tuple[str, str]) -> None:
        interp = _TABLE[key]
        assert interp.impact.strip(), f"Empty impact for {key}"

    @pytest.mark.parametrize("key", list(_TABLE.keys()))
    def test_remediation_is_non_empty(self, key: tuple[str, str]) -> None:
        interp = _TABLE[key]
        assert interp.remediation.strip(), f"Empty remediation for {key}"

    @pytest.mark.parametrize("key", [k for k in _TABLE if k[1] == "fail"])
    def test_fail_impact_mentions_ai_agents(self, key: tuple[str, str]) -> None:
        """Fail interpretations must explain consequences for AI agents specifically."""
        interp = _TABLE[key]
        text = interp.impact.lower()
        assert "agent" in text or "ai" in text, (
            f"Fail impact for {key} doesn't mention 'agent' or 'AI' — "
            f"must explain business consequence for AI agent operators."
        )

    def test_auth_fail_has_reproduce_command(self) -> None:
        """Auth failure must include a curl reproduce command — it's the most critical check."""
        interp = _TABLE[("auth_token", "fail")]
        assert interp.reproduce, "auth_token fail must have a reproduce command"
        assert "curl" in interp.reproduce

    def test_auth_fail_has_owasp_reference(self) -> None:
        interp = _TABLE[("auth_token", "fail")]
        assert interp.refs is not None
        assert any("owasp" in ref.lower() for ref in interp.refs), (
            "auth_token fail must reference OWASP API Security"
        )


# ---------------------------------------------------------------------------
# interpret_all convenience wrapper
# ---------------------------------------------------------------------------

class TestInterpretAll:
    def test_returns_dict_keyed_by_check_name(self) -> None:
        results = [
            _make("latency_p95", True, 100),
            _make("auth_token", False, 0),
        ]
        out = interpret_all(results)
        assert set(out.keys()) == {"latency_p95", "auth_token"}

    def test_unknown_check_maps_to_none(self) -> None:
        results = [_make("unknown_check", False, 0)]
        out = interpret_all(results)
        assert out["unknown_check"] is None

    def test_na_check_gets_na_interpretation(self) -> None:
        results = [_make_na("schema")]
        out = interpret_all(results)
        interp = out["schema"]
        assert interp is not None
        assert "Not applicable" in interp.impact


# ---------------------------------------------------------------------------
# CheckInterpretation dataclass
# ---------------------------------------------------------------------------

class TestCheckInterpretationDataclass:
    def test_frozen(self) -> None:
        c = CheckInterpretation(impact="x", remediation="y")
        with pytest.raises((AttributeError, TypeError)):
            c.impact = "changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        c = CheckInterpretation(impact="x", remediation="y")
        assert c.reproduce == ""
        assert c.refs is None
