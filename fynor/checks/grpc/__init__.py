"""gRPC service agent-readiness checks"""

from fynor.checks.grpc.reflection import check_reflection_enabled

ALL_CHECKS = [
    check_reflection_enabled,
]

__all__ = ["check_reflection_enabled", "ALL_CHECKS"]