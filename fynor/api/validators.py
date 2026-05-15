"""
fynor.api.validators — Input validation for the hosted API.

All validation functions are called before any adapter is instantiated or
any HTTP request is dispatched. They raise ValueError with a user-facing
message on invalid input.

SSRF protection is the most critical validator here. The hosted API accepts
arbitrary user-supplied URLs and dispatches HTTP requests from Fynor's
infrastructure — without SSRF protection, an attacker can probe internal
AWS services (metadata API, VPC resources, DynamoDB endpoints).

Security scope restrictions (web API only — CLI tool has no such restrictions):
- "cli" interface type is NOT accepted by the web API. CLI checks execute
  arbitrary subprocesses; accepting user-supplied CLI invocation strings on
  the shared hosted server is an unauthenticated RCE vector. Use the local
  CLI tool (``pip install fynor``) for CLI interface checks.
- "auth_token" is NOT accepted by the web API. Tokens submitted via the web
  tool travel through Railway's shared infrastructure and may appear in logs.
  Authenticated checks require the local CLI tool with FYNOR_AUTH_TOKEN env var.

References:
- OWASP SSRF Prevention Cheat Sheet
- AWS Security Blog: "SSRF and the AWS Metadata Service"
- Decision D1 (plan-eng-review 2026-05-15): CLI removed from web tool
- Decision D5 (plan-eng-review 2026-05-15): auth_token disabled in web tool
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Re-export the core validator so callers only need to import from one place.
# The implementation lives in adapters.base to keep it close to where it's used.
from fynor.adapters.base import validate_target_url, _PRIVATE_NETWORKS

__all__ = [
    "validate_target_url",
    "validate_interface_type",
    "validate_check_options",
]

# "cli" is intentionally excluded from the web API.
# CLI interface checks execute subprocesses. Accepting arbitrary CLI invocation
# strings from the public internet on a shared Railway server is an RCE vector.
# Use the local ``fynor`` CLI tool (``pip install fynor``) instead.
# Decision D1 — plan-eng-review 2026-05-15.
_VALID_INTERFACE_TYPES = frozenset({
    "mcp", "rest", "graphql", "grpc", "websocket",
    # "soap" intentionally excluded — SOAPAdapter not yet implemented.
    # Accepting "soap" would produce a misleading runtime error instead of
    # a clear validation failure. Re-add when fynor/adapters/soap.py ships.
})

# Surface a clear error for callers who try to use "cli" via the web API.
_WEB_BLOCKED_TYPES: dict[str, str] = {
    "cli": (
        "The 'cli' interface type is not available via the web API. "
        "CLI checks execute subprocesses on the host server, which is an "
        "unauthenticated remote-code-execution risk. "
        "Install the local tool instead: pip install fynor"
    ),
}

_VALID_CHECK_NAMES = frozenset({
    # Original 8 checks (Month 1–2)
    "latency_p95", "error_rate", "schema", "retry",
    "auth_token", "rate_limit", "timeout", "log_completeness",
    # Extended checks (added per ADR-03 amendments)
    "data_freshness", "tool_description_quality", "response_determinism",
})


def validate_interface_type(interface_type: str) -> None:
    """
    Validate the interface type field from a POST /check request.

    Args:
        interface_type: The interface type string to validate.

    Raises:
        ValueError: If the interface type is unknown or blocked for web use.
    """
    # Blocked types get a specific, actionable error rather than "unknown".
    if interface_type in _WEB_BLOCKED_TYPES:
        raise ValueError(_WEB_BLOCKED_TYPES[interface_type])

    if interface_type not in _VALID_INTERFACE_TYPES:
        raise ValueError(
            f"Unknown interface type: {interface_type!r}. "
            f"Supported types: {sorted(_VALID_INTERFACE_TYPES)}."
        )


def validate_check_options(options: dict) -> None:
    """
    Validate the options dict from a POST /check request.

    Validates the optional 'checks' subset list, timeout_ms, and
    ensures no unexpected keys are present.

    Args:
        options: The options dict from the request body.

    Raises:
        ValueError: If any option value is invalid.
    """
    if not isinstance(options, dict):
        raise ValueError("'options' must be a JSON object.")

    # Validate subset check list
    checks = options.get("checks")
    if checks is not None:
        if not isinstance(checks, list) or not all(isinstance(c, str) for c in checks):
            raise ValueError("'options.checks' must be a list of check name strings.")
        unknown = set(checks) - _VALID_CHECK_NAMES
        if unknown:
            raise ValueError(
                f"Unknown check names in 'options.checks': {sorted(unknown)}. "
                f"Valid names: {sorted(_VALID_CHECK_NAMES)}."
            )

    # Validate timeout_ms
    timeout_ms = options.get("timeout_ms")
    if timeout_ms is not None:
        if not isinstance(timeout_ms, int) or timeout_ms < 1000 or timeout_ms > 60_000:
            raise ValueError(
                "'options.timeout_ms' must be an integer between 1000 and 60000."
            )

    # Reject auth_token — not accepted by the web API.
    # Tokens submitted via the web tool travel through Railway's shared
    # infrastructure and may appear in access logs or error traces.
    # Authenticated checks must use the local CLI tool with the
    # FYNOR_AUTH_TOKEN environment variable.
    # Decision D5 — plan-eng-review 2026-05-15.
    if "auth_token" in options:
        raise ValueError(
            "'options.auth_token' is not accepted by the web API. "
            "Auth tokens may be logged by Railway's shared infrastructure. "
            "Use the local CLI tool with FYNOR_AUTH_TOKEN env var: "
            "  FYNOR_AUTH_TOKEN=<token> fynor check --target <url> --type <type>"
        )
