"""
fynor.checks.mcp.retry — Check 4: Retry and malformed-request behaviour.

Sends a malformed JSON-RPC request (missing required fields) and verifies
the server returns a structured error rather than crashing or silently
returning 200. An agent that cannot distinguish success from failure on
malformed input will compound errors across its entire pipeline.

Pass: 400 or JSON-RPC error object returned on malformed input.
Score:
  Correct 400/422                    → 100
  JSON-RPC error on 200              →  70  (pass, acceptable per spec)
  2xx with no error field            →  20  (fail — silent success on bad input)
  5xx crash                          →   0  (fail — server cannot recover)
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

# Intentionally missing required "jsonrpc" and "method" fields
_MALFORMED_PAYLOAD: dict = {"id": 1}


def check_retry(adapter: BaseAdapter) -> CheckResult:
    """
    Send a malformed JSON-RPC request and verify the server handles it.

    Returns:
        CheckResult with check="retry", value=http_status_code.
    """
    response = adapter.call(_MALFORMED_PAYLOAD)

    # Best case: explicit HTTP error code
    if response.status_code in (400, 422):
        return CheckResult(
            check="retry",
            passed=True,
            score=100,
            value=response.status_code,
            detail=(
                f"Correctly returned HTTP {response.status_code} on malformed request. "
                "Agent can detect and recover."
            ),
        )

    # Acceptable: JSON-RPC error object on 200
    if (
        response.status_code == 200
        and isinstance(response.body, dict)
        and "error" in response.body
    ):
        return CheckResult(
            check="retry",
            passed=True,
            score=70,
            value=200,
            detail=(
                "Server returned JSON-RPC error object on malformed request "
                "(HTTP 200, but error field present — acceptable per JSON-RPC 2.0 spec)."
            ),
        )

    # Server crash — worst case for agents
    if response.status_code >= 500:
        return CheckResult(
            check="retry",
            passed=False,
            score=0,
            value=response.status_code,
            detail=(
                f"Server returned {response.status_code} on malformed input. "
                "A 5xx crash on bad input means agents cannot self-recover — "
                "one malformed call corrupts the entire pipeline."
            ),
        )

    # Silent success — agent cannot detect the error
    return CheckResult(
        check="retry",
        passed=False,
        score=20,
        value=response.status_code,
        detail=(
            f"Server returned {response.status_code} with no error signal on malformed input. "
            "Agent treats this as success — silent corruption."
        ),
    )
