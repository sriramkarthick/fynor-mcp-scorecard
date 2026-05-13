"""
fynor.checks.mcp.timeout — Check 7: Timeout handling.

Re-runs the probe with a strict 5-second client timeout and verifies
the server either responds in time or returns a graceful error.
An agent connected to a hanging endpoint blocks its entire pipeline
indefinitely — there is no worse failure mode.

Pass: server responds within 5s (any response including 5xx is OK here).
Score:
  Response ≤ 2000ms   → 100
  Response ≤ 5000ms   →  75
  Graceful error body →  50   (server responded, just slow)
  Hard hang / timeout →   0   (pipeline blocker)
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.adapters.mcp import MCPAdapter
from fynor.adapters.rest import RESTAdapter
from fynor.history import CheckResult


def check_timeout(adapter: BaseAdapter) -> CheckResult:
    """
    Probe the target with a 5-second timeout and check the response.

    Returns:
        CheckResult with check="timeout", value=latency_ms or None.
    """
    # Create a tight-timeout copy of the adapter
    tight = _make_tight_adapter(adapter, timeout=5.0)
    response = tight.call()

    # Hard hang — worst case
    if response.error and "timeout" in response.error.lower():
        return CheckResult(
            check="timeout",
            passed=False,
            score=0,
            value=None,
            detail=(
                "Server did not respond within 5 seconds (hard timeout). "
                "Agents block indefinitely on this endpoint — "
                "pipeline hangs until the orchestrator's own timeout fires."
            ),
        )

    # Fast response — best case
    if response.latency_ms <= 2000 and response.error is None:
        return CheckResult(
            check="timeout",
            passed=True,
            score=100,
            value=round(response.latency_ms, 2),
            detail=f"Fast response: {response.latency_ms:.0f}ms (well within 5s threshold).",
        )

    # Slow but within 5s
    if response.latency_ms <= 5000 and response.error is None:
        return CheckResult(
            check="timeout",
            passed=True,
            score=75,
            value=round(response.latency_ms, 2),
            detail=(
                f"Slow response: {response.latency_ms:.0f}ms — within 5s threshold but "
                "latency is high. Consider optimising for sustained agent workloads."
            ),
        )

    # Connection error but not timeout — some graceful signal received
    return CheckResult(
        check="timeout",
        passed=True,
        score=50,
        value=round(response.latency_ms, 2),
        detail=(
            f"Server responded with error ({response.error or response.status_code}) "
            "but did not hard-hang. Graceful degradation confirmed."
        ),
    )


def _make_tight_adapter(adapter: BaseAdapter, timeout: float) -> BaseAdapter:
    """Return a copy of the adapter with a tighter timeout."""
    if isinstance(adapter, MCPAdapter):
        return MCPAdapter(adapter.target, timeout=timeout,
                          auth_token=getattr(adapter, "_auth_token", None))
    if isinstance(adapter, RESTAdapter):
        return RESTAdapter(adapter.target, timeout=timeout,
                           method=adapter._method,
                           auth_token=getattr(adapter, "_auth_token", None),
                           probe_path=adapter._probe_path)
    # Generic fallback — same class, same target, tighter timeout
    return type(adapter)(adapter.target, timeout=timeout)
