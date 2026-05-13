"""
fynor.checks.mcp.error_rate — Check 2: Error rate over 50-request window.

Sends 50 requests at 1 req/s and measures the non-2xx response rate.
Agent workloads are continuous — even a 5% error rate compounding across
50+ tool calls in a pipeline causes observable failures.

Pass threshold: error rate < 5%
Score:
  0%    → 100
  < 2%  →  90
  < 5%  →  70  (pass threshold)
  < 10% →  40
  ≥ 10% →   0
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

_N_REQUESTS = 50
_PASS_THRESHOLD_PCT = 5.0


def check_error_rate(adapter: BaseAdapter) -> CheckResult:
    """
    Measure error rate over a 50-request window at 1 req/s.

    Returns:
        CheckResult with check="error_rate", value=error_rate_percent.
    """
    responses = adapter.burst(n=_N_REQUESTS, rps=1.0)
    error_count = sum(1 for r in responses if not r.ok)
    rate = (error_count / _N_REQUESTS) * 100.0
    passed = rate < _PASS_THRESHOLD_PCT

    if rate == 0:
        score = 100
    elif rate < 2:
        score = 90
    elif rate < 5:
        score = 70
    elif rate < 10:
        score = 40
    else:
        score = 0

    return CheckResult(
        check="error_rate",
        passed=passed,
        score=score,
        value=round(rate, 2),
        detail=(
            f"Error rate: {rate:.1f}% ({error_count}/{_N_REQUESTS} requests failed). "
            f"Threshold: {_PASS_THRESHOLD_PCT}%."
        ),
    )
