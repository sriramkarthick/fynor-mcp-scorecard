"""
fynor.checks.mcp.timeout — Check 7: Timeout handling.

Sends a probe with a strict 5-second client timeout and verifies
the server either responds in time or returns a graceful error.
A hanging endpoint blocks an agent's entire pipeline indefinitely —
there is no worse failure mode in a synchronous agent workflow.

Scoring:
  Response ≤ 2000ms   → 100   (well within agent pipeline budgets)
  Response ≤ 5000ms   →  75   (pass — acceptable, consider optimising)
  Hard hang / timeout →   0   (fail — pipeline blocker)
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.adapters.mcp import MCPAdapter
from fynor.adapters.rest import RESTAdapter
from fynor.history import CheckResult

_TIGHT_TIMEOUT_S = 5.0   # client-side timeout for this check
_FAST_THRESHOLD_MS = 2000.0


async def check_timeout(adapter: BaseAdapter) -> CheckResult:
    """
    Probe the target with a 5-second timeout and check the response.

    Returns:
        CheckResult with check="timeout", value=latency_ms or None.
    """
    tight = _make_tight_adapter(adapter, timeout=_TIGHT_TIMEOUT_S)
    response = await tight.call()

    base_ev: dict[str, object] = {
        "timeout_budget_s": _TIGHT_TIMEOUT_S,
        "fast_threshold_ms": _FAST_THRESHOLD_MS,
        "response_latency_ms": round(response.latency_ms, 1) if response.latency_ms else None,
        "response_error": response.error,
        "response_status": response.status_code if not response.error else None,
    }

    # Hard hang — worst case
    if response.error and "timeout" in response.error.lower():
        return CheckResult(
            check="timeout",
            passed=False,
            score=0,
            value=None,
            detail=(
                f"Server did not respond within {_TIGHT_TIMEOUT_S:.0f}s (hard timeout). "
                "Agents block indefinitely on this endpoint — the pipeline hangs "
                "until the orchestrator's own timeout fires, aborting everything upstream. "
                "Ensure the server responds (even with an error) within 5 seconds."
            ),
            evidence={**base_ev, "hung": True},
        )

    # Connection error (not timeout) — some graceful signal received
    if response.error:
        return CheckResult(
            check="timeout",
            passed=True,
            score=75,
            value=round(response.latency_ms, 2),
            detail=(
                f"Server returned a connection error quickly ({response.latency_ms:.0f}ms): "
                f"{response.error}. "
                "Graceful degradation confirmed — agent can detect the failure and move on."
            ),
            evidence={**base_ev, "hung": False},
        )

    # Fast response — best case
    if response.latency_ms <= _FAST_THRESHOLD_MS:
        return CheckResult(
            check="timeout",
            passed=True,
            score=100,
            value=round(response.latency_ms, 2),
            detail=(
                f"Fast response: {response.latency_ms:.0f}ms "
                f"(well within {_TIGHT_TIMEOUT_S:.0f}s threshold)."
            ),
            evidence={**base_ev, "hung": False},
        )

    # Slow but within timeout window
    return CheckResult(
        check="timeout",
        passed=True,
        score=75,
        value=round(response.latency_ms, 2),
        detail=(
            f"Slow response: {response.latency_ms:.0f}ms — within the "
            f"{_TIGHT_TIMEOUT_S:.0f}s threshold but high for agent workloads. "
            "Consider optimising for P95 response times under 2000ms."
        ),
        evidence={**base_ev, "hung": False},
    )


def _make_tight_adapter(adapter: BaseAdapter, timeout: float) -> BaseAdapter:
    """Return a copy of the adapter with the tighter timeout for this check."""
    if isinstance(adapter, MCPAdapter):
        return MCPAdapter(
            adapter.target,
            timeout=timeout,
            auth_token=getattr(adapter, "_auth_token", None),
        )
    if isinstance(adapter, RESTAdapter):
        return RESTAdapter(
            adapter.target,
            timeout=timeout,
            method=adapter._method,
            auth_token=getattr(adapter, "_auth_token", None),
            probe_path=adapter._probe_path,
        )
    # Generic fallback — same type, same target, tighter timeout
    return type(adapter)(adapter.target, timeout=timeout)
