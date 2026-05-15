"""WebSocket agent-readiness checks"""

from fynor.checks.websocket.keepalive import check_keepalive_interval

ALL_CHECKS = [
    check_keepalive_interval,
]

__all__ = ["check_keepalive_interval", "ALL_CHECKS"]