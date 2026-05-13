"""
fynor.checks.mcp.retry — Check 4: Retry and malformed-request behaviour.

Sends malformed JSON-RPC requests (missing required fields) and verifies
the server returns a structured error rather than crashing or silently
returning 200. An agent cannot distinguish success from failure on
malformed input — it will propagate bad state through its entire pipeline.

Two malformed payloads per ADR-03:
  1. Null method: {"jsonrpc": "2.0", "method": null, "id": 1}
  2. Missing id:  {"jsonrpc": "2.0", "method": "test"}

Score is the average of both sub-check scores.

Scoring:
  400 / 422 with JSON-RPC error object → 100   (correct: agent can detect + recover)
  400 / 422 with plain error text       →  80   (acceptable: HTTP code signals failure)
  200 with JSON-RPC error object        →  60   (pass — valid per JSON-RPC 2.0 spec)
  2xx with no error field               →  20   (fail — silent success on bad input)
  5xx crash                             →   0   (fail — server cannot self-recover)
  Timeout / connection error            →   0   (fail — pipeline blocker)
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

# ADR-03: two malformed payloads test different invalid states
_MALFORMED_NULL_METHOD: dict = {"jsonrpc": "2.0", "method": None, "id": 1}
_MALFORMED_MISSING_ID: dict = {"jsonrpc": "2.0", "method": "test"}


async def check_retry(adapter: BaseAdapter) -> CheckResult:
    """
    Send two malformed JSON-RPC requests and verify graceful error handling.

    Returns:
        CheckResult with check="retry", value=average_sub_score.
    """
    score_1, detail_1 = await _probe(adapter, _MALFORMED_NULL_METHOD, "null method")
    score_2, detail_2 = await _probe(adapter, _MALFORMED_MISSING_ID, "missing id")

    avg_score = int((score_1 + score_2) / 2)
    passed = avg_score >= 60

    if score_1 == score_2 == 100:
        detail = (
            "Both malformed requests (null method, missing id) returned "
            "correct HTTP 4xx errors with JSON-RPC error objects. "
            "Agents can detect and recover from malformed-input failures."
        )
    elif passed:
        detail = (
            f"Malformed-input handling is acceptable. "
            f"Null-method probe: {detail_1}. "
            f"Missing-id probe: {detail_2}."
        )
    else:
        detail = (
            f"Malformed-input handling is insufficient — agent pipeline risk. "
            f"Null-method probe: {detail_1}. "
            f"Missing-id probe: {detail_2}."
        )

    return CheckResult(
        check="retry",
        passed=passed,
        score=avg_score,
        value=avg_score,
        detail=detail,
    )


async def _probe(
    adapter: BaseAdapter, payload: dict, label: str
) -> tuple[int, str]:
    """Send one malformed probe and return (score, detail_fragment)."""
    response = await adapter.call(payload)

    if response.error:
        return 0, f"{label}: connection error — {response.error}"

    status = response.status_code

    # Correct: explicit HTTP error with JSON-RPC error body
    if status in (400, 422) and isinstance(response.body, dict) and "error" in response.body:
        return 100, f"{label}: HTTP {status} + JSON-RPC error object (correct)"

    # Acceptable: explicit HTTP error (plain text is still actionable)
    if status in (400, 422):
        return 80, f"{label}: HTTP {status} (no JSON-RPC error body, but status signals failure)"

    # Valid per spec: 200 with JSON-RPC error object
    if status == 200 and isinstance(response.body, dict) and "error" in response.body:
        return 60, f"{label}: HTTP 200 + JSON-RPC error object (valid but non-standard)"

    # Server crash — worst case for agent pipelines
    if status >= 500:
        return 0, (
            f"{label}: HTTP {status} crash on malformed input — "
            "one bad agent call will corrupt the pipeline"
        )

    # Silent success — agent cannot detect the error
    return 20, (
        f"{label}: HTTP {status} with no error signal — "
        "agent treats malformed input as success"
    )
