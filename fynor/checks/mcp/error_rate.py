"""
fynor.checks.mcp.error_rate — Check 2: Error rate over 50-request window.

Sends 50 requests at 1 req/s and measures the non-2xx response rate.
Agent workloads are continuous — a 5% error rate compounding across 50+
tool calls in a pipeline guarantees at least one failure in 92% of runs.

Scoring (ADR-02, locked via check-implementation-contract.md):
  0%          → 100
  > 0% ≤ 1%  →  90
  > 1% ≤ 5%  →  60   (pass threshold: score ≥ 60)
  > 5% ≤ 10% →  30
  > 10%       →   0

HTTP 429 responses are NOT counted as errors — they indicate rate limiting
(checked separately by rate_limit). HTTP 4xx other than 429 ARE errors.
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

# ADR-04: 50 requests gives binomial standard error of ±3.1% at the 5% threshold.
_N_REQUESTS = 50
# ADR-04: sequential at 1 req/s stays below most free-tier rate limits.
_RPS = 1.0
# Pass threshold: error rate ≤ 5% → score ≥ 60.
_PASS_THRESHOLD_PCT = 5.0


async def check_error_rate(adapter: BaseAdapter) -> CheckResult:
    """
    Measure error rate over a 50-request window at 1 req/s.

    Returns:
        CheckResult with check="error_rate", value=error_rate_percent.
    """
    responses = await adapter.burst(n=_N_REQUESTS, rps=_RPS)

    # HTTP 429 is not an error — it is a rate-limit signal (separate check)
    error_count = sum(
        1 for r in responses
        if not r.ok and r.status_code != 429
    )
    rate = (error_count / _N_REQUESTS) * 100.0
    score = _score_from_rate(rate)
    passed = rate <= _PASS_THRESHOLD_PCT

    rate_limited_count = sum(1 for r in responses if r.status_code == 429)
    rl_note = (
        f" ({rate_limited_count} requests rate-limited — not counted as errors)"
        if rate_limited_count
        else ""
    )

    return CheckResult(
        check="error_rate",
        passed=passed,
        score=score,
        value=round(rate, 2),
        detail=(
            f"Error rate: {rate:.1f}% ({error_count}/{_N_REQUESTS} requests failed){rl_note}. "
            f"Pass threshold: ≤{_PASS_THRESHOLD_PCT:.0f}%."
        ),
    )


def _score_from_rate(rate: float) -> int:
    """
    Convert error rate percentage to a score.

    Bands are locked in check-implementation-contract.md — do not adjust
    without filing an ADR-02 amendment.
    """
    if rate == 0.0:
        return 100
    if rate <= 1.0:
        return 90
    if rate <= 5.0:
        return 60
    if rate <= 10.0:
        return 30
    return 0
