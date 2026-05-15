"""
fynor.checks.graphql.introspection — Check: introspection_enabled.

GraphQL introspection exposes the full schema to any caller. Enabling it in
production is a security risk. Most hardened production APIs (Shopify, GitHub,
Stripe) disable it.

Result semantics (decision D12 — plan-eng-review 2026-05-15):
  - Introspection enabled with valid schema → pass (score 100)
    Useful for development APIs or APIs that explicitly choose to expose schema.
  - Introspection disabled (400 / 403 / errors array, no data) → result="na"
    Not a failure. Disabling introspection is a security best practice.
    Weight redistributed to other applicable checks.
  - Connection error or unexpected status → fail (score 0)
    Server is not reachable or behaving unexpectedly.

Why na instead of pass: returning "pass" would mean Fynor actively endorses
disabling introspection (not its job). Returning "fail" would penalise
hardened production APIs (credibility killer). "na" correctly models
"this check is not applicable to this server's configuration."
"""

from __future__ import annotations

from fynor.adapters.graphql import GraphQLAdapter
from fynor.history import CheckResult


async def check_introspection_enabled(adapter: GraphQLAdapter) -> CheckResult:
    """
    Check whether GraphQL introspection is enabled.

    Args:
        adapter: A GraphQLAdapter pointed at the target endpoint.

    Returns:
        CheckResult with check="introspection_enabled".
        result="na" when introspection is disabled (not a failure).
        result="pass" when introspection returns a valid schema.
        result="fail" when the server is unreachable or returns an error.
    """
    r = await adapter.introspect()

    # Transport error — cannot reach server
    if r.error:
        return CheckResult(
            check="introspection_enabled",
            passed=False,
            score=0,
            result="fail",
            value=None,
            detail=f"Connection error probing introspection: {r.error}",
        )

    body = r.body

    # Non-200 status that indicates introspection is blocked
    if r.status_code in (400, 403, 405):
        return _introspection_disabled(
            detail=(
                f"Introspection query returned HTTP {r.status_code}. "
                "Introspection is disabled on this server — this is a "
                "security best practice. Check not scored (result: na)."
            )
        )

    # GraphQL errors array with no data field — introspection explicitly disabled
    if isinstance(body, dict):
        has_data = "data" in body and body["data"] is not None
        has_errors = bool(body.get("errors"))

        if has_errors and not has_data:
            first_error = body["errors"][0] if body["errors"] else {}
            msg = first_error.get("message", "")
            return _introspection_disabled(
                detail=(
                    f"Introspection disabled: server returned errors with no data. "
                    f"First error: {msg!r}. "
                    "This is a security best practice. Check not scored (result: na)."
                )
            )

        # data.__schema present → introspection is enabled
        if has_data and isinstance(body.get("data"), dict):
            schema = body["data"].get("__schema")
            if isinstance(schema, dict):
                type_count = len(schema.get("types", []))
                return CheckResult(
                    check="introspection_enabled",
                    passed=True,
                    score=100,
                    result="pass",
                    value=type_count,
                    detail=(
                        f"Introspection enabled: schema returned {type_count} types. "
                        "Consider disabling introspection in production (security best practice)."
                    ),
                )

    # Unexpected response shape — server responded but not with GraphQL JSON
    return CheckResult(
        check="introspection_enabled",
        passed=False,
        score=0,
        result="fail",
        value=r.status_code,
        detail=(
            f"Unexpected response to introspection query (HTTP {r.status_code}). "
            f"Expected a GraphQL JSON envelope with 'data' or 'errors'. "
            f"Got: {str(body)[:120]!r}"
        ),
    )


def _introspection_disabled(detail: str) -> CheckResult:
    """Return the standard na result for introspection-disabled servers."""
    return CheckResult(
        check="introspection_enabled",
        passed=True,   # Not a failure — good security practice
        score=0,       # Excluded from scoring via result="na"
        result="na",
        value=None,
        detail=detail,
    )
