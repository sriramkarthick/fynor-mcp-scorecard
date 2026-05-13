"""
fynor.checks.mcp.schema — Check 3: MCP spec compliance.

Validates JSON-RPC 2.0 envelope on a live response. Every MCP response
must contain: jsonrpc="2.0", id (matching request), and exactly one of
result or error. A schema violation means the agent's parser will break
silently on every call.

Pass: all required fields present and mutually exclusive.
Score:
  All correct         → 100
  One issue           →  60
  Multiple issues     →   0
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult


def check_schema(adapter: BaseAdapter) -> CheckResult:
    """
    Validate the JSON-RPC 2.0 envelope on a live MCP response.

    Returns:
        CheckResult with check="schema", value=issue_count.
    """
    response = adapter.call()
    body = response.body

    if not isinstance(body, dict):
        return CheckResult(
            check="schema",
            passed=False,
            score=0,
            value=None,
            detail=(
                f"Response body is not JSON (got {type(body).__name__}). "
                "MCP requires JSON-RPC 2.0 envelope."
            ),
        )

    issues: list[str] = []

    if body.get("jsonrpc") != "2.0":
        issues.append(
            f"Missing or invalid 'jsonrpc' field "
            f"(got {body.get('jsonrpc')!r}, expected '2.0')."
        )

    if "id" not in body:
        issues.append("Missing 'id' field in JSON-RPC response.")

    has_result = "result" in body
    has_error = "error" in body

    if not has_result and not has_error:
        issues.append("Response has neither 'result' nor 'error' field.")
    if has_result and has_error:
        issues.append(
            "Response has both 'result' and 'error' fields "
            "(mutually exclusive per JSON-RPC 2.0 spec)."
        )

    passed = len(issues) == 0
    score = 100 if passed else 60 if len(issues) == 1 else 0
    detail = (
        "MCP schema valid: JSON-RPC 2.0 compliant."
        if passed
        else " | ".join(issues)
    )

    return CheckResult(
        check="schema",
        passed=passed,
        score=score,
        value=len(issues),
        detail=detail,
    )
