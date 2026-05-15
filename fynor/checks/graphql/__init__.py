"""GraphQL API agent-readiness checks"""

from fynor.checks.graphql.introspection import check_introspection_enabled

ALL_CHECKS = [
    check_introspection_enabled,
]

__all__ = ["check_introspection_enabled", "ALL_CHECKS"]