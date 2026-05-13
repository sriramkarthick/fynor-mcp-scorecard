"""
fynor.checks.mcp.latency — Check 1: Response time P95.

Sends 20 sequential requests to the MCP server and computes the 95th
percentile latency. Agent workloads are sustained, not bursty — P95 under
sequential load is the correct measure for agent reliability (ADR-03).

Why sequential? ADR-04: concurrent requests inflate latency artificially
and do not model how a single AI agent calls a tool.
Why P95? ADR-03: P50 hides tail behaviour; P99 over 20 requests is
statistically unstable (determined by one data point).
Why 20 requests? ADR-04: the 19th-highest latency is stable and reproducible.

Scoring:
  P95 ≤  500ms  → 100
  P95 ≤ 1000ms  →  75
  P95 ≤ 2000ms  →  50   (pass threshold: score ≥ 50, P95 < 2000ms)
  P95 ≤ 3000ms  →  25
  P95 > 3000ms  →   0

Minimum sample: if fewer than 10 of 20 requests succeed, score = 0
(insufficient data to compute a reliable P95).
"""

from __future__ import annotations

import statistics

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

# Thresholds — locked in ADR-04. Do not change without a superseding ADR.
_PASS_THRESHOLD_MS = 2000.0
_N_REQUESTS = 20
_MIN_SUCCESSFUL = 10  # minimum successful responses for a valid P95 estimate
_RPS = 2.0            # 2 req/s = 500ms interval, preserves sequential behaviour


async def check_latency_p95(adapter: BaseAdapter) -> CheckResult:
    """
    Measure P95 latency under 20 sequential requests.

    Args:
        adapter: Any BaseAdapter subclass pointed at the target interface.

    Returns:
        CheckResult with:
          check   = "latency_p95"
          value   = P95 latency in milliseconds (float), or None if all failed
          passed  = True when P95 < 2000ms
          score   = 0–100 (see module docstring for bands)
          detail  = human-readable description including threshold comparison
    """
    responses = await adapter.burst(n=_N_REQUESTS, rps=_RPS)

    # Collect latencies from successful (non-error) responses only
    latencies = [r.latency_ms for r in responses if r.error is None]
    error_count = sum(1 for r in responses if r.error is not None)

    if len(latencies) < _MIN_SUCCESSFUL:
        return CheckResult(
            check="latency_p95",
            passed=False,
            score=0,
            value=None,
            detail=(
                f"Insufficient sample: only {len(latencies)}/{_N_REQUESTS} requests "
                f"succeeded (need ≥{_MIN_SUCCESSFUL}). "
                "P95 cannot be reliably computed — investigate connectivity."
            ),
        )

    # P95: sort values, take the 95th percentile position
    p95 = statistics.quantiles(latencies, n=100)[94]
    score = _score_from_p95(p95)
    passed = p95 < _PASS_THRESHOLD_MS

    error_note = f" ({error_count} requests failed — excluded from P95)" if error_count else ""

    return CheckResult(
        check="latency_p95",
        passed=passed,
        score=score,
        value=round(p95, 2),
        detail=(
            f"P95 latency: {p95:.0f}ms over {len(latencies)} successful "
            f"requests{error_note}. "
            f"Pass threshold: <{_PASS_THRESHOLD_MS:.0f}ms."
        ),
    )


def _score_from_p95(p95_ms: float) -> int:
    """
    Map P95 latency to a 0-100 score.

    Bands reflect agent pipeline requirements: a 500ms P95 is agent-safe;
    above 2000ms the pipeline blocker risk becomes unacceptable.
    """
    if p95_ms <= 500:
        return 100
    if p95_ms <= 1000:
        return 75
    if p95_ms <= 2000:
        return 50
    if p95_ms <= 3000:
        return 25
    return 0
