"""
fynor.checks.websocket.keepalive — Check: keepalive_interval.

Verifies that a WebSocket server responds to PING control frames within the
negotiated keepalive interval (default 10 seconds).

Decision D2 (plan-eng-review 2026-05-15):
  Old design: check if server sends a ping within 60 seconds.
  Bug: total pipeline timeout is 45 seconds — the check could never pass.
  Fix: the adapter sends a PING and measures time-to-PONG. Interval is 10s
  by default, overridable by the server's X-Keepalive-Interval header.

Scoring:
  PONG received within interval  → score 100  (pass)
  PONG not received / timeout    → score 0    (fail)
  Connection refused / error     → score 0    (fail)

Why not na: keepalive is a universal WebSocket check — every WebSocket
server must respond to PING frames per RFC 6455 §5.5.2. A server that
ignores PING frames is non-compliant. There is no na case here.
"""

from __future__ import annotations

from fynor.adapters.websocket import WebSocketAdapter
from fynor.history import CheckResult


async def check_keepalive_interval(adapter: WebSocketAdapter) -> CheckResult:
    """
    Check that the server responds to a WebSocket PING within the negotiated interval.

    Sends a PING control frame (RFC 6455 §5.5.2) and waits for the PONG.
    The deadline is adapter.negotiated_keepalive_interval (10s default,
    or the value from the server's X-Keepalive-Interval header).

    Args:
        adapter: A WebSocketAdapter pointed at the target endpoint.

    Returns:
        CheckResult with check="keepalive_interval".
        result="pass" when PONG arrives within the deadline.
        result="fail" when PONG does not arrive or connection fails.
    """
    r = await adapter._measure_ping_pong()
    interval = adapter.negotiated_keepalive_interval

    # -- PONG received within interval --------------------------------------
    if r.status_code == 200 and isinstance(r.body, dict):
        pong_ms = r.body.get("pong_latency_ms", r.latency_ms)
        return CheckResult(
            check="keepalive_interval",
            passed=True,
            score=100,
            result="pass",
            value=pong_ms,
            detail=(
                f"PONG received in {pong_ms:.0f}ms "
                f"(keepalive interval: {interval:.0f}s). "
                "WebSocket connection maintains keepalive correctly."
            ),
        )

    # -- Timeout: no PONG within interval -----------------------------------
    if r.status_code == 504:
        return CheckResult(
            check="keepalive_interval",
            passed=False,
            score=0,
            result="fail",
            value=None,
            detail=(
                f"No PONG received within {interval:.0f}s keepalive interval. "
                f"Error: {r.error or 'timeout'}. "
                "Server may not support WebSocket PING/PONG (RFC 6455 §5.5.2), "
                "or the connection is too slow to respond within the interval. "
                "Set X-Keepalive-Interval header on the server to advertise a longer interval."
            ),
        )

    # -- Connection / transport failure -------------------------------------
    return CheckResult(
        check="keepalive_interval",
        passed=False,
        score=0,
        result="fail",
        value=r.status_code,
        detail=(
            f"Could not establish WebSocket connection "
            f"(HTTP-equivalent {r.status_code}). "
            f"Error: {r.error or 'unknown'}. "
            "Verify the target URL is a WebSocket endpoint and the server is reachable."
        ),
    )
