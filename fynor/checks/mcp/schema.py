"""
fynor.checks.mcp.schema — Check 3: MCP spec compliance.

Validates JSON-RPC 2.0 envelope on a live response. Every MCP response
must contain: jsonrpc="2.0", id (matching request), and exactly one of
result or error. A schema violation means the agent's parser will break
silently on every call.

Scoring:
  All required fields present, correct types → 100   (pass)
  One structural issue                        →  60   (pass — agent can adapt)
  Multiple issues or not JSON                 →   0   (fail — agent cannot recover)

Why worst-case over 3 probes: ADR-03 "correctness under non-human input"
requires the check to be conservative. One bad response out of three is enough
to fail — agents hit the same code path repeatedly.
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult


async def check_schema(adapter: BaseAdapter) -> CheckResult:
    """
    Validate the JSON-RPC 2.0 envelope on a live MCP response.

    Sends 3 probe requests and uses the worst-case result.

    Returns:
        CheckResult with check="schema", value=max_issue_count_across_3_probes.
    """
    worst_issues: list[str] = []
    worst_score = 100

    for _ in range(3):
        response = await adapter.call()
        body = response.body

        if not isinstance(body, dict):
            # Not JSON at all — worst possible result, stop early
            return CheckResult(
                check="schema",
                passed=False,
                score=0,
                value=None,
                detail=(
                    f"Response body is not JSON (got {type(body).__name__!r}). "
                    "MCP requires a JSON-RPC 2.0 envelope on every response. "
                    "Ensure Content-Type: application/json is set."
                ),
            )

        issues = _validate_envelope(body)
        score = 100 if not issues else 60 if len(issues) == 1 else 0

        if score < worst_score:
            worst_score = score
            worst_issues = issues

    passed = worst_score >= 60
    detail = (
        "MCP schema valid: JSON-RPC 2.0 compliant on all 3 probes."
        if not worst_issues
        else " | ".join(worst_issues)
    )

    return CheckResult(
        check="schema",
        passed=passed,
        score=worst_score,
        value=len(worst_issues),
        detail=detail,
    )


def _validate_envelope(body: dict) -> list[str]:
    """Return a list of JSON-RPC 2.0 envelope violations."""
    issues: list[str] = []

    if body.get("jsonrpc") != "2.0":
        issues.append(
            f"'jsonrpc' field must be exactly '2.0' (string), "
            f"got {body.get('jsonrpc')!r}."
        )

    if "id" not in body:
        issues.append("Missing 'id' field in JSON-RPC response.")

    has_result = "result" in body
    has_error = "error" in body

    if not has_result and not has_error:
        issues.append(
            "Response has neither 'result' nor 'error' field. "
            "JSON-RPC 2.0 requires exactly one."
        )
    elif has_result and has_error:
        issues.append(
            "Response has both 'result' and 'error' fields. "
            "These are mutually exclusive per JSON-RPC 2.0 §5."
        )

    return issues
