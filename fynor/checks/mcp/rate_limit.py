"""
fynor.checks.mcp.rate_limit — Check 6: Rate limit compliance.

Sends a 50-request burst at 20 req/s and verifies the server signals
rate limiting with HTTP 429 and a Retry-After header. Agents calling at
machine speed will hit rate limits — without a 429, they cannot back off
and will flood the endpoint until it fails.

Pass: at least one 429 response received during burst.
Score:
  429 + Retry-After header   → 100   (agent knows exactly when to retry)
  429 without Retry-After    →  60   (pass — agent knows to back off, not when)
  No 429, no crashes         →  30   (fail — server silently absorbs or drops)
  5xx errors during burst    →   0   (fail — rate limit disguised as server crash)
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

_BURST_N = 50
_BURST_RPS = 20.0


def check_rate_limit(adapter: BaseAdapter) -> CheckResult:
    """
    Burst 50 requests at 20 req/s and verify rate limit signalling.

    Returns:
        CheckResult with check="rate_limit", value=count_of_429_responses.
    """
    responses = adapter.burst(n=_BURST_N, rps=_BURST_RPS)

    rate_limited = [r for r in responses if r.status_code == 429]
    crashed = [r for r in responses if r.status_code >= 500]

    # Server crashes before rate limiting — worst case
    if crashed and not rate_limited:
        return CheckResult(
            check="rate_limit",
            passed=False,
            score=0,
            value=len(crashed),
            detail=(
                f"Server returned {len(crashed)} 5xx errors under {_BURST_RPS} req/s burst "
                "with no 429 rate limit signal. "
                "Agent cannot distinguish rate limiting from server crash."
            ),
        )

    # No rate limiting detected
    if not rate_limited:
        return CheckResult(
            check="rate_limit",
            passed=False,
            score=30,
            value=0,
            detail=(
                f"No 429 returned in {_BURST_N}-request burst at {_BURST_RPS} req/s. "
                "Server may silently drop requests or lack rate limiting entirely. "
                "Agent has no signal to back off."
            ),
        )

    # 429 present — check for Retry-After
    has_retry_after = any(
        "retry-after" in {k.lower() for k in r.headers}
        for r in rate_limited
    )

    if has_retry_after:
        return CheckResult(
            check="rate_limit",
            passed=True,
            score=100,
            value=len(rate_limited),
            detail=(
                f"Rate limiting correct: {len(rate_limited)} 429 responses "
                "with Retry-After header. Agent can compute exact backoff."
            ),
        )

    return CheckResult(
        check="rate_limit",
        passed=True,
        score=60,
        value=len(rate_limited),
        detail=(
            f"{len(rate_limited)} 429 responses returned without Retry-After header. "
            "Agent can detect rate limiting but cannot determine backoff duration. "
            "Add Retry-After: <seconds> to improve agent behaviour."
        ),
    )
