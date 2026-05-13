"""
fynor.checks.mcp.rate_limit — Check 6: Rate limit compliance.

Sends a 50-request burst at 20 req/s and verifies the server signals
rate limiting with HTTP 429 and a Retry-After header. Agents calling at
machine speed will hit rate limits — without a 429, they cannot back off
and will flood the endpoint until it fails or until their own timeout fires.

Why 20 req/s? ADR-03: below DoS thresholds, above normal human usage.
The User-Agent header is set to "Fynor-Reliability-Checker/1.0" so that
operators can whitelist or log these requests separately.

Scoring:
  429 + Retry-After header   → 100   (agent computes exact backoff)
  429 without Retry-After    →  60   (pass — agent knows to back off, not when)
  No 429, no 5xx             →  30   (fail — server absorbs silently)
  5xx errors during burst     →   0   (fail — rate limit disguised as crash)
"""

from __future__ import annotations

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

_BURST_N = 50
_BURST_RPS = 20.0


async def check_rate_limit(adapter: BaseAdapter) -> CheckResult:
    """
    Burst 50 requests at 20 req/s and verify rate limit signalling.

    Returns:
        CheckResult with check="rate_limit", value=count_of_429_responses.
    """
    responses = await adapter.burst(n=_BURST_N, rps=_BURST_RPS)

    rate_limited = [r for r in responses if r.status_code == 429]
    crashed = [r for r in responses if r.status_code >= 500]

    # 5xx before any 429 — server crashes under load, cannot self-protect
    if crashed and not rate_limited:
        return CheckResult(
            check="rate_limit",
            passed=False,
            score=0,
            value=len(crashed),
            detail=(
                f"Server returned {len(crashed)} HTTP 5xx errors under "
                f"{_BURST_RPS:.0f} req/s burst with no 429 rate-limit signal. "
                "Agents cannot distinguish rate limiting from server failure. "
                "Implement rate limiting that returns 429 before the server saturates."
            ),
        )

    # No rate limiting detected — server silently absorbs or drops
    if not rate_limited:
        return CheckResult(
            check="rate_limit",
            passed=False,
            score=30,
            value=0,
            detail=(
                f"No 429 returned in {_BURST_N}-request burst at {_BURST_RPS:.0f} req/s. "
                "Server may silently absorb excess requests or lack rate limiting entirely. "
                "Without a 429 + Retry-After signal, agents have no backoff cue and will "
                "continue flooding the endpoint."
            ),
        )

    # 429 present — check for Retry-After header for precise backoff
    has_retry_after = any(
        "retry-after" in {k.lower() for k in r.headers}
        for r in rate_limited
    )

    first_429_at = next(
        (i + 1 for i, r in enumerate(responses) if r.status_code == 429), None
    )

    if has_retry_after:
        return CheckResult(
            check="rate_limit",
            passed=True,
            score=100,
            value=len(rate_limited),
            detail=(
                f"Rate limiting correct: {len(rate_limited)} HTTP 429 responses "
                f"(first at request #{first_429_at}) with Retry-After header. "
                "Agents can compute exact backoff duration."
            ),
        )

    return CheckResult(
        check="rate_limit",
        passed=True,
        score=60,
        value=len(rate_limited),
        detail=(
            f"{len(rate_limited)} HTTP 429 responses (first at request #{first_429_at}) "
            "returned without Retry-After header. "
            "Agents detect rate limiting but cannot determine backoff duration. "
            "Add 'Retry-After: <seconds>' to 429 responses to complete agent support."
        ),
    )
