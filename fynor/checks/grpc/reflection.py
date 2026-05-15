"""
fynor.checks.grpc.reflection — Check: reflection_enabled.

gRPC server reflection lets clients discover which services and methods a
server exposes without out-of-band proto files. Most production servers
disable it (it's a potential information-disclosure surface).

Result semantics (Decision D3 — plan-eng-review 2026-05-15):
  - Reflection available, lists services → pass (score 100)
  - Reflection disabled (UNIMPLEMENTED), no grpc_method configured → na
    Not applicable. Disabling reflection is a valid deployment choice.
  - Reflection disabled (UNIMPLEMENTED), grpc_method configured → probe that
    method instead. If probe succeeds → pass. If probe fails → fail.
  - Server unreachable / UNAVAILABLE / DEADLINE_EXCEEDED → fail (score 0)

Why na not fail for UNIMPLEMENTED (same logic as GraphQL introspection D12):
  Penalising gRPC servers for disabling reflection would fail every hardened
  production service. The check is "can we discover the server's capabilities?"
  — if that information is intentionally locked down, the check simply doesn't
  apply to this server's configuration.
"""

from __future__ import annotations

from fynor.adapters.grpc import GRPCAdapter
from fynor.history import CheckResult

# HTTP status codes that signal "reflection intentionally disabled"
_UNIMPLEMENTED_CODES = {501}   # StatusCode.UNIMPLEMENTED → 501


async def check_reflection_enabled(adapter: GRPCAdapter) -> CheckResult:
    """
    Check whether gRPC server reflection is enabled.

    Falls back to probing adapter.grpc_method when reflection is
    disabled and a fallback method is configured.

    Args:
        adapter: A GRPCAdapter pointed at the target endpoint.

    Returns:
        CheckResult with check="reflection_enabled".
        result="na"   when reflection is disabled and no fallback method set.
        result="pass" when reflection succeeds or fallback probe succeeds.
        result="fail" when server is unreachable or both probes fail.
    """
    r = await adapter._call_reflection_service()

    # -- Reflection available -----------------------------------------------
    if r.status_code == 200 and isinstance(r.body, dict):
        services = r.body.get("services", [])
        count = len(services)
        names_preview = ", ".join(services[:5])
        if len(services) > 5:
            names_preview += f" … (+{len(services) - 5} more)"
        return CheckResult(
            check="reflection_enabled",
            passed=True,
            score=100,
            result="pass",
            value=count,
            detail=(
                f"Reflection enabled: {count} service(s) discovered. "
                f"Services: {names_preview}"
            ),
        )

    # -- Reflection intentionally disabled (UNIMPLEMENTED) ------------------
    if r.status_code in _UNIMPLEMENTED_CODES or (
        r.error and "UNIMPLEMENTED" in r.error
    ):
        return await _handle_reflection_disabled(adapter)

    # -- Real failure (UNAVAILABLE, DEADLINE_EXCEEDED, etc.) ----------------
    return CheckResult(
        check="reflection_enabled",
        passed=False,
        score=0,
        result="fail",
        value=r.status_code,
        detail=(
            f"Could not reach gRPC server (HTTP-equivalent {r.status_code}). "
            f"Error: {r.error or 'unknown'}. "
            "Verify the target is reachable and the port is correct."
        ),
    )


async def _handle_reflection_disabled(adapter: GRPCAdapter) -> CheckResult:
    """
    Called when the server returned UNIMPLEMENTED for reflection.

    If adapter.grpc_method is configured, probe that specific method as a
    fallback connectivity check. Otherwise return na.
    """
    if not adapter.grpc_method:
        return CheckResult(
            check="reflection_enabled",
            passed=True,    # Not a failure — deliberate deployment choice
            score=0,        # Excluded from scoring via result="na"
            result="na",
            value=None,
            detail=(
                "Reflection is disabled on this server (StatusCode.UNIMPLEMENTED). "
                "This is a common production configuration — not scored (result: na). "
                "To get a connectivity signal, set 'grpc_method' in your check request "
                "(e.g. 'grpc.health.v1.Health/Check')."
            ),
        )

    # Fallback: probe the user-specified method
    fallback = await adapter.call()

    if fallback.status_code == 200:
        return CheckResult(
            check="reflection_enabled",
            passed=True,
            score=100,
            result="pass",
            value=None,
            detail=(
                f"Reflection disabled, but method probe succeeded: "
                f"'{adapter.grpc_method}' returned OK. "
                "Server is reachable and responding to gRPC calls."
            ),
        )

    return CheckResult(
        check="reflection_enabled",
        passed=False,
        score=0,
        result="fail",
        value=fallback.status_code,
        detail=(
            f"Reflection disabled and method probe '{adapter.grpc_method}' "
            f"failed (HTTP-equivalent {fallback.status_code}). "
            f"Error: {fallback.error or 'unknown'}. "
            "Verify the method name and that the server is reachable."
        ),
    )
