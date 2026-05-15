"""
fynor/profiles.py — Context-specific check profiles.

A profile overrides the pass threshold for specific checks without changing
their scoring functions. The score for each check is computed identically
regardless of profile; the profile only re-evaluates whether that score
counts as passed=True or passed=False.

Usage:
    from fynor.profiles import get_profile, apply_profile
    profile = get_profile("security")
    results = apply_profile(raw_results, profile)

Built-in profiles:
  default    — Standard thresholds for general-purpose MCP servers and APIs.
  security   — Stricter thresholds for security operations MCP servers.
  financial  — Stricter thresholds for financial/regulated MCP servers (SOC 2 / PCI DSS).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fynor.history import CheckResult


@dataclass(frozen=True)
class CheckProfile:
    """
    Context-specific pass threshold overrides.

    pass_thresholds maps check_name → minimum score required to pass.
    Checks not in this dict use their own default pass threshold.
    """
    name: str
    description: str
    pass_thresholds: dict[str, int] = field(default_factory=dict)


DEFAULT_PROFILE = CheckProfile(
    name="default",
    description="Standard reliability thresholds for general-purpose MCP servers and APIs.",
    pass_thresholds={},
)

SECURITY_PROFILE = CheckProfile(
    name="security",
    description=(
        "Stricter thresholds for MCP servers used in security operations. "
        "Error tolerance is near-zero; data must be fresh; responses must be deterministic."
    ),
    pass_thresholds={
        "error_rate": 90,             # ≤1% errors required (default pass: ≤5%)
        "latency_p95": 80,            # P95 ≤500ms required (default pass: ≤2000ms)
        "data_freshness": 80,         # data age ≤60min required (default pass: ≤24h)
        "response_determinism": 100,  # full consistency required (default pass: 2/3)
        "auth_token": 100,            # unchanged — already requires 100
        "tool_description_quality": 80,  # adequate descriptions required (default: 60)
    },
)

FINANCIAL_PROFILE = CheckProfile(
    name="financial",
    description=(
        "Stricter thresholds for MCP servers used in financial operations. "
        "Optimised for SOC 2 Type II and PCI DSS compliance requirements."
    ),
    pass_thresholds={
        "error_rate": 90,      # ≤1% errors
        "auth_token": 100,     # unchanged
        "log_completeness": 100,  # JSON logs + timestamp required
        "data_freshness": 80,  # data age ≤60min
        "schema": 100,         # perfect schema conformance
    },
)

PROFILES: dict[str, CheckProfile] = {
    "default": DEFAULT_PROFILE,
    "security": SECURITY_PROFILE,
    "financial": FINANCIAL_PROFILE,
}


def get_profile(name: str) -> CheckProfile:
    """Return a named profile. Raises ValueError for unknown names."""
    if name not in PROFILES:
        available = ", ".join(sorted(PROFILES.keys()))
        raise ValueError(f"Unknown profile '{name}'. Available: {available}")
    return PROFILES[name]


def apply_profile(results: list[CheckResult], profile: CheckProfile) -> list[CheckResult]:
    """
    Re-evaluate passed/failed on results using profile-specific thresholds.

    For each check in results: if the profile specifies a threshold for that check,
    re-compute passed = (score >= threshold). Otherwise, keep original passed value.

    Args:
        results: List of CheckResult objects from a single check run.
        profile: The profile to apply.

    Returns:
        New list of CheckResult objects with updated passed fields.
    """
    if not profile.pass_thresholds:
        return results

    updated: list[CheckResult] = []
    for r in results:
        threshold = profile.pass_thresholds.get(r.check)
        if threshold is not None:
            updated.append(CheckResult(
                check=r.check,
                passed=r.score >= threshold,
                score=r.score,
                value=r.value,
                detail=r.detail,
                result=r.result,
            ))
        else:
            updated.append(r)
    return updated
