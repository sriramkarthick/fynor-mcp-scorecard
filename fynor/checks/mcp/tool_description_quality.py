"""
fynor/checks/mcp/tool_description_quality.py — Check #10: tool_description_quality

Validates that tools returned by tools/list have descriptions and inputSchema
complete enough for an AI model to select and invoke them correctly.

Scoring (worst-case across all tools — one inadequate tool fails the check):
  All tools: name + description ≥50 chars + inputSchema with typed params  → 100
  All tools: name + description ≥20 chars + inputSchema present            → 80
  All tools: name + description ≥10 chars (no inputSchema)                 → 60  ← pass
  Any tool:  description absent or < 10 chars                              → 20
  No tools returned / tools/list fails / any tool missing name             → 0

ADR-03 signal class: Reliability — tool discoverability
Pass threshold: score ≥ 60 (all tools have name + description ≥10 chars)

result.value: count of fully-described tools (description ≥50 chars + typed inputSchema).
result.detail: names of inadequate tools, or confirmation of full coverage.
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

CHECK_NAME = "tool_description_quality"

_MIN_DESC_PASSING = 10
_MIN_DESC_ADEQUATE = 20
_MIN_DESC_FULL = 50


def _score_one_tool(tool: dict) -> tuple[int, str]:
    """Score a single tool dict. Returns (score, reason_string)."""
    name = (tool.get("name") or "").strip()
    if not name:
        return 0, "tool has no name field"

    desc = (tool.get("description") or "").strip()
    input_schema = tool.get("inputSchema") or tool.get("input_schema")

    if len(desc) < _MIN_DESC_PASSING:
        return 20, f"'{name}': description missing or < {_MIN_DESC_PASSING} chars"

    has_typed_params = False
    if input_schema and isinstance(input_schema, dict):
        props = input_schema.get("properties", {})
        if props and all("type" in v for v in props.values() if isinstance(v, dict)):
            has_typed_params = True

    if len(desc) >= _MIN_DESC_FULL and has_typed_params:
        return 100, f"'{name}': complete"
    if len(desc) >= _MIN_DESC_ADEQUATE and input_schema:
        return 80, f"'{name}': adequate"
    return 60, f"'{name}': description present, no inputSchema"


async def check_tool_description_quality(adapter: BaseAdapter) -> CheckResult:
    """Call tools/list and assess the description quality of every tool."""
    try:
        response = await adapter.call(
            payload={"jsonrpc": "2.0", "method": "tools/list", "id": 1, "params": {}}
        )
    except Exception as exc:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=0,
            detail=f"tools/list call failed: {exc}",
        )

    if response.status_code != 200 or not response.body:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=0,
            detail=f"tools/list returned HTTP {response.status_code} with empty body.",
        )

    body = response.body
    if not isinstance(body, dict):
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=0,
            detail=(
                f"tools/list returned non-JSON body (type={type(body).__name__!r}). "
                "MCP servers must return application/json with a JSON-RPC 2.0 envelope."
            ),
        )
    result_data = body.get("result", {})
    if isinstance(result_data, dict):
        tools = result_data.get("tools", [])
    elif isinstance(result_data, list):
        tools = result_data
    else:
        tools = []

    if not tools:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=0,
            detail=(
                "tools/list returned no tools. "
                "MCP servers must expose at least one tool with a description."
            ),
        )

    scores = []
    reasons = []
    fully_described = 0

    for tool in tools:
        if not isinstance(tool, dict):
            scores.append(0)
            reasons.append("non-dict entry in tools list")
            continue
        s, r = _score_one_tool(tool)
        scores.append(s)
        reasons.append(r)
        if s == 100:
            fully_described += 1

    worst_score = min(scores)
    passed = worst_score >= 60

    inadequate = [r for s, r in zip(scores, reasons) if s < 80]
    if inadequate:
        detail = (
            f"{fully_described}/{len(tools)} tools fully described. "
            f"Issues: {'; '.join(inadequate[:5])}. "
            f"Pass threshold: all tools need name + description (≥{_MIN_DESC_PASSING} chars)."
        )
    else:
        detail = (
            f"All {len(tools)} tools adequately described. "
            f"{fully_described} with full descriptions + typed inputSchema."
        )

    return CheckResult(
        check=CHECK_NAME, passed=passed, score=worst_score,
        value=fully_described, detail=detail,
    )
