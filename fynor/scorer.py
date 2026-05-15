"""
fynor.scorer — Weighted reliability grade engine.

ADR-02 (locked): Security 30% + Reliability 40% + Performance 30%.
A critical security failure caps the overall grade at D, regardless of other scores.

Grade bands:
  A   90–100   Agent-ready. Safe to use in production.
  B   75–89    Minor issues. Safe with monitoring.
  C   60–74    Moderate issues. Investigate before production.
  D   45–59    Significant failures. Not recommended for agents.
  F   0–44     Critical failures. Do not use.

Security cap rule (ADR-02):
  If auth_token or any security check scores 0, final grade cannot exceed D.
  This prevents a fast server with broken auth from grading as B or C.

11 deterministic checks:
  Security    (auth_token)
  Reliability (error_rate, schema, retry, timeout, log_completeness,
               data_freshness, tool_description_quality, response_determinism)
  Performance (latency_p95, rate_limit)
"""

from __future__ import annotations

from dataclasses import dataclass

from fynor.history import CheckResult


# ADR-02: weight categories — locked, do not change without an ADR.
_CHECK_CATEGORY: dict[str, str] = {
    "latency_p95":              "performance",
    "error_rate":               "reliability",
    "schema":                   "reliability",
    "retry":                    "reliability",
    "auth_token":               "security",
    "rate_limit":               "performance",
    "timeout":                  "reliability",
    "log_completeness":         "reliability",
    "data_freshness":           "reliability",
    "tool_description_quality": "reliability",
    "response_determinism":     "reliability",
}

_CATEGORY_WEIGHT: dict[str, float] = {
    "security":    0.30,
    "reliability": 0.40,
    "performance": 0.30,
}

_SECURITY_CHECKS = {"auth_token"}   # extend as security checks are added
_GRADE_BANDS = [
    (90, "A"),
    (75, "B"),
    (60, "C"),
    (45, "D"),
    (0,  "F"),
]


@dataclass
class ScorecardResult:
    """Full scored output for one check run against one target."""

    target: str
    interface_type: str
    grade: str                          # A | B | C | D | F
    weighted_score: float               # 0.0–100.0
    security_score: float
    reliability_score: float
    performance_score: float
    checks: list[CheckResult]
    security_capped: bool = False       # True if ADR-02 cap was applied
    summary: str = ""


def score(
    target: str,
    interface_type: str,
    results: list[CheckResult],
) -> ScorecardResult:
    """
    Compute a weighted grade from a list of CheckResult objects.

    Checks with result="na" are excluded from category averages. When a
    category has zero scored (non-na) checks, its weight is redistributed
    equally to the non-empty categories (decision D8/T10 — 2026-05-15).

    Args:
        target:         URL or identifier of the checked interface.
        interface_type: Interface type string (mcp | rest | graphql | …).
        results:        All CheckResult objects from a single check run.

    Returns:
        ScorecardResult with grade, weighted score, per-category scores,
        and whether the ADR-02 security cap was applied.
        Grade is "N/A" when every check returns result="na".
    """
    by_category: dict[str, list[int]] = {
        "security": [],
        "reliability": [],
        "performance": [],
    }

    for r in results:
        if r.result == "na":
            continue  # Not applicable — exclude from scoring entirely
        category = _CHECK_CATEGORY.get(r.check, "reliability")
        by_category[category].append(r.score)

    # All-na run → special grade
    if not any(by_category.values()):
        return ScorecardResult(
            target=target,
            interface_type=interface_type,
            grade="N/A",
            weighted_score=0.0,
            security_score=0.0,
            reliability_score=0.0,
            performance_score=0.0,
            checks=results,
            security_capped=False,
            summary="No applicable checks for this interface type.",
        )

    def avg(scores: list[int]) -> float | None:
        """None when category has no scored checks (weight gets redistributed)."""
        return sum(scores) / len(scores) if scores else None

    sec_avg  = avg(by_category["security"])
    rel_avg  = avg(by_category["reliability"])
    perf_avg = avg(by_category["performance"])

    # Redistribute weight from empty categories to non-empty ones
    base_weights = dict(_CATEGORY_WEIGHT)  # copy — do not mutate the module constant
    avgs = {
        "security":    sec_avg,
        "reliability": rel_avg,
        "performance": perf_avg,
    }
    weights = _redistribute_weights(base_weights, avgs)

    weighted = sum(
        avg_val * weights[cat]
        for cat, avg_val in avgs.items()
        if avg_val is not None
    )

    # ADR-02 security cap: any security check at 0 → max grade D.
    # Fires AFTER redistribution (security weight may have grown from redistribution,
    # but the cap is on the final weighted score, not on the weight itself).
    security_capped = any(
        r.score == 0 for r in results
        if r.check in _SECURITY_CHECKS and r.result != "na"
    )
    if security_capped:
        weighted = min(weighted, 59.0)

    grade = _letter_grade(weighted)
    summary = _build_summary(grade, results, security_capped)

    # Per-category scores for the report: 0.0 when category was all-na
    return ScorecardResult(
        target=target,
        interface_type=interface_type,
        grade=grade,
        weighted_score=round(weighted, 1),
        security_score=round(sec_avg or 0.0, 1),
        reliability_score=round(rel_avg or 0.0, 1),
        performance_score=round(perf_avg or 0.0, 1),
        checks=results,
        security_capped=security_capped,
        summary=summary,
    )


def _redistribute_weights(
    base: dict[str, float],
    avgs: dict[str, float | None],
) -> dict[str, float]:
    """
    Distribute weight from empty (all-na) categories to non-empty ones.

    Empty categories contribute 0 weight; their share is split equally
    among the non-empty categories.

    Args:
        base:  Base category weights (must sum to 1.0).
        avgs:  Per-category averages; None means the category is empty (all-na).

    Returns:
        Adjusted weight dict. Empty categories have weight 0.0.
        Non-empty categories have their base weight plus an equal share
        of the redistributed weight.
    """
    empty_cats = [cat for cat, avg in avgs.items() if avg is None]
    scored_cats = [cat for cat, avg in avgs.items() if avg is not None]

    if not empty_cats:
        return dict(base)  # Nothing to redistribute

    freed_weight = sum(base[cat] for cat in empty_cats)
    bonus_per_cat = freed_weight / len(scored_cats) if scored_cats else 0.0

    result: dict[str, float] = {}
    for cat in avgs:
        if cat in empty_cats:
            result[cat] = 0.0
        else:
            result[cat] = base[cat] + bonus_per_cat
    return result


def _letter_grade(score: float) -> str:
    for threshold, grade in _GRADE_BANDS:
        if score >= threshold:
            return grade
    return "F"


def _build_summary(
    grade: str,
    results: list[CheckResult],
    capped: bool,
) -> str:
    scored = [r for r in results if r.result != "na"]
    failed = [r for r in scored if not r.passed]
    if not failed:
        return f"Grade {grade}: all checks passed."

    failed_names = ", ".join(r.check for r in failed)
    cap_note = " [ADR-02 security cap applied]" if capped else ""
    return f"Grade {grade}: {len(failed)}/{len(scored)} checks failed ({failed_names}).{cap_note}"
