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

Scoring (step function — no interpolation, per check-implementation-contract.md):
  P95 ≤  200ms  → 100
  P95 ≤  500ms  →  80
  P95 ≤ 1000ms  →  60   (pass threshold: score ≥ 60, P95 ≤ 1000ms)
  P95 > 1000ms  →   0

Rationale: 1000ms P95 is the agent pipeline budget from ADR-04.
Above 1000ms, agents risk cascading timeout failures in multi-tool workflows.

Minimum sample: if fewer than 10 of 20 requests succeed, score = 0
(insufficient data to compute a reliable P95).
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

# Thresholds — locked in check-implementation-contract.md §1.
# Do not change without updating the contract document.
_PASS_THRESHOLD_MS = 1000.0   # P95 must be ≤ 1000ms to pass
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
            evidence={
                "probe_count": _N_REQUESTS,
                "successful_count": len(latencies),
                "error_count": error_count,
                "latencies_ms": [round(ms, 1) for ms in sorted(latencies)],
            },
        )

    # P95: sort the 20 values, take the 19th value (0-indexed = index 18).
    # This is the deterministic formula from check-implementation-contract.md §1.
    # No interpolation — same server state always produces the same index.
    sorted_latencies = sorted(latencies)
    p95_idx = max(0, int(len(sorted_latencies) * 0.95) - 1)
    p95 = sorted_latencies[p95_idx]
    score = _score_from_p95(p95)
    passed = score >= 60   # pass threshold: score ≥ 60

    error_note = f" ({error_count} requests failed — excluded from P95)" if error_count else ""

    return CheckResult(
        check="latency_p95",
        passed=passed,
        score=score,
        value=round(p95, 2),
        detail=(
            f"P95 latency: {p95:.0f}ms over {len(latencies)} successful "
            f"requests{error_note}. "
            f"Pass threshold: ≤{_PASS_THRESHOLD_MS:.0f}ms."
        ),
        evidence={
            "probe_count": _N_REQUESTS,
            "successful_count": len(latencies),
            "error_count": error_count,
            # All 20 measured latencies in sorted order — these are the real numbers
            # from this client's server, not averages or estimates.
            "latencies_ms_sorted": [round(ms, 1) for ms in sorted_latencies],
            "p95_ms": round(p95, 1),
            "p95_index": p95_idx,          # which position in sorted array is P95
            "min_ms": round(sorted_latencies[0], 1),
            "max_ms": round(sorted_latencies[-1], 1),
            "pass_threshold_ms": _PASS_THRESHOLD_MS,
        },
    )


def _score_from_p95(p95_ms: float) -> int:
    """
    Map P95 latency to a 0-100 score.

    Step function (no interpolation) — locked in check-implementation-contract.md §1.
    Bands reflect agent pipeline requirements: 1000ms P95 is the outer limit
    for safe single-tool invocation in a multi-step agent workflow.
    """
    if p95_ms <= 200:
        return 100
    if p95_ms <= 500:
        return 80
    if p95_ms <= 1000:
        return 60
    return 0
