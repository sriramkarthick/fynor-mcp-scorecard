"""
fynor.checks.mcp.latency — Check 1: Response time P95.

Sends 20 sequential requests to the MCP server and computes the 95th
percentile latency. Agent workloads are sustained, not bursty — P95 under
sequential load is the correct measure for agent reliability.

Pass threshold: P95 < 2000ms
Score curve:
  P95 ≤  500ms  →  100
  P95 ≤ 1000ms  →   75
  P95 ≤ 2000ms  →   50  (pass threshold)
  P95 ≤ 3000ms  →   25
  P95 >  3000ms  →    0
"""

from __future__ import annotations

import statistics

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

# Thresholds in milliseconds
_PASS_THRESHOLD_MS = 2000.0
_N_REQUESTS = 20


def check_latency_p95(adapter: BaseAdapter) -> CheckResult:
    """
    Measure P95 latency under 20 sequential requests.

    Args:
        adapter: Any BaseAdapter subclass pointed at the target interface.

    Returns:
        CheckResult with:
          check   = "latency_p95"
          value   = P95 latency in milliseconds (float)
          passed  = True when P95 < 2000ms
          score   = 0–100 (see module docstring for curve)
          detail  = human-readable description
    """
    responses = adapter.burst(n=_N_REQUESTS, rps=2.0)

    # Collect latencies from successful responses only
    latencies = [r.latency_ms for r in responses if r.error is None]

    if not latencies:
        return CheckResult(
            check="latency_p95",
            passed=False,
            score=0,
            value=None,
            detail=f"All {_N_REQUESTS} requests failed — no latency data collected.",
        )

    p95 = statistics.quantiles(latencies, n=100)[94] if len(latencies) >= 20 else max(latencies)
    score = _score_from_p95(p95)
    passed = p95 < _PASS_THRESHOLD_MS

    error_count = sum(1 for r in responses if r.error is not None)
    error_note = f" ({error_count} requests failed)" if error_count else ""

    return CheckResult(
        check="latency_p95",
        passed=passed,
        score=score,
        value=round(p95, 2),
        detail=(
            f"P95 latency: {p95:.0f}ms over {len(latencies)} successful requests{error_note}. "
            f"Threshold: {_PASS_THRESHOLD_MS:.0f}ms."
        ),
    )


def _score_from_p95(p95_ms: float) -> int:
    if p95_ms <= 500:
        return 100
    if p95_ms <= 1000:
        return 75
    if p95_ms <= 2000:
        return 50
    if p95_ms <= 3000:
        return 25
    return 0
