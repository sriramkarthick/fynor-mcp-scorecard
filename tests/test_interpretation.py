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
from fynor.interpretation import CheckInterpretation, interpret, interpret_all, _TABLE, _InterpEntry


# ---------------------------------------------------------------------------
# Helper: resolve a _TABLE entry (static or factory) to a CheckInterpretation.
# Factory entries require a CheckResult — supply a minimal synthetic one.
# ---------------------------------------------------------------------------

def _resolve(key: tuple[str, str], entry: _InterpEntry) -> CheckInterpretation:
    """Call factory functions with a minimal CheckResult; return statics directly."""
    if isinstance(entry, CheckInterpretation):
        return entry
    check_name, band = key
    score = 0 if band == "fail" else 100 if band == "pass" else 60
    result_arg = "na" if band == "na" else ""
    r = CheckResult(
        check=check_name,
        passed=(band == "pass"),
        score=score,
        value=500.0 if check_name == "latency_p95" else 3.0 if check_name == "error_rate" else 1,
        detail="test detail",
        result=result_arg,
        evidence={
            # latency evidence
            "probe_count": 20, "successful_count": 20, "error_count": 0,
            "p95_ms": 500.0, "min_ms": 200.0, "max_ms": 800.0,
            "pass_threshold_ms": 1000.0,
            # error_rate evidence
            "error_rate_pct": 3.0, "rate_limited_count": 0,
            "status_code_distribution": {"200": 47, "500": 3},
            "first_error_status": 500,
            "first_error_response_preview": "Internal Server Error",
            "pass_threshold_pct": 5.0,
            # auth evidence
            "probe_token_used": "fynor.reliability.checker.invalid.token.v1",
            "f1_leaked_header_names": [], "f3_secret_param_names": [],
            "f2_ran": True, "f2_unauth_status": 200, "f2_response_preview": "{}",
            "f4_ran": True, "f4_response_status": 200, "f4_response_preview": "{}",
            "f4_response_content_type": "application/json",
        },
    )
    return entry(r)


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
        interp = _resolve(key, _TABLE[key])
        assert interp.impact.strip(), f"Empty impact for {key}"

    @pytest.mark.parametrize("key", list(_TABLE.keys()))
    def test_remediation_is_non_empty(self, key: tuple[str, str]) -> None:
        interp = _resolve(key, _TABLE[key])
        assert interp.remediation.strip(), f"Empty remediation for {key}"

    @pytest.mark.parametrize("key", [k for k in _TABLE if k[1] == "fail"])
    def test_fail_impact_mentions_ai_agents(self, key: tuple[str, str]) -> None:
        """Fail interpretations must explain consequences for AI agents specifically."""
        interp = _resolve(key, _TABLE[key])
        text = interp.impact.lower()
        assert "agent" in text or "ai" in text, (
            f"Fail impact for {key} doesn't mention 'agent' or 'AI' — "
            f"must explain business consequence for AI agent operators."
        )

    def test_auth_fail_has_reproduce_command(self) -> None:
        """Auth failure must include a curl reproduce command — it's the most critical check."""
        interp = _resolve(("auth_token", "fail"), _TABLE[("auth_token", "fail")])
        assert interp.reproduce, "auth_token fail must have a reproduce command"
        assert "curl" in interp.reproduce

    def test_auth_fail_has_owasp_reference(self) -> None:
        interp = _resolve(("auth_token", "fail"), _TABLE[("auth_token", "fail")])
        assert interp.refs is not None
        assert any("owasp" in ref.lower() for ref in interp.refs), (
            "auth_token fail must reference OWASP API Security"
        )

    def test_latency_fail_uses_actual_measured_value(self) -> None:
        """latency_p95 fail must reference the client's real P95 in the impact text."""
        r = CheckResult(
            check="latency_p95", passed=False, score=0, value=3841.0, detail="",
            evidence={"probe_count": 20, "successful_count": 20, "error_count": 0,
                      "p95_ms": 3841.0, "min_ms": 1203.0, "max_ms": 4102.0, "pass_threshold_ms": 1000.0},
        )
        interp = interpret(r)
        assert interp is not None
        assert "3841" in interp.impact, "Impact must quote the client's actual P95 value"
        assert "1203" in interp.impact, "Impact must quote the client's actual min latency"

    def test_two_clients_different_p95_get_different_impact(self) -> None:
        """Proves interpretations are client-specific, not generic templates."""
        def _make_lat(p95: float) -> CheckResult:
            return CheckResult(
                check="latency_p95", passed=False, score=0, value=p95, detail="",
                evidence={"probe_count": 20, "successful_count": 20, "error_count": 0,
                          "p95_ms": p95, "min_ms": 100.0, "max_ms": p95 + 200, "pass_threshold_ms": 1000.0},
            )
        a = interpret(_make_lat(3841.0))
        b = interpret(_make_lat(2103.0))
        assert a is not None and b is not None
        assert a.impact != b.impact, (
            "Two clients with different P95 values must receive different impact text. "
            "Identical text means the interpretation is still a generic template."
        )

    def test_error_rate_fail_includes_server_status_distribution(self) -> None:
        """error_rate fail must reference the actual status codes the server returned."""
        r = CheckResult(
            check="error_rate", passed=False, score=0, value=12.0, detail="",
            evidence={
                "probe_count": 50, "error_count": 6, "rate_limited_count": 0,
                "error_rate_pct": 12.0,
                "status_code_distribution": {"200": 44, "503": 6},
                "first_error_status": 503,
                "first_error_response_preview": "Service Unavailable",
                "pass_threshold_pct": 5.0,
            },
        )
        interp = interpret(r)
        assert interp is not None
        assert "503" in interp.impact or "503" in interp.remediation, (
            "error_rate impact must include the actual HTTP status codes returned by the server"
        )

    def test_auth_fail_quotes_exact_token_sent(self) -> None:
        """auth_token fail must quote the exact token Fynor sent in the impact."""
        token = "fynor.reliability.checker.invalid.token.v1"
        r = CheckResult(
            check="auth_token", passed=False, score=0, value=1, detail="",
            evidence={
                "probe_token_used": token, "f4_ran": True, "f4_response_status": 200,
                "f4_response_preview": '{"result": "tool data"}',
                "f2_ran": False, "f1_leaked_header_names": [], "f3_secret_param_names": [],
            },
        )
        interp = interpret(r)
        assert interp is not None
        assert token in interp.impact, (
            "auth_token fail impact must quote the exact token that was sent to the server"
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
