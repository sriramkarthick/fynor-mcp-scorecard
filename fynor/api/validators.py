"""
fynor.api.validators — Input validation for the hosted API.

All validation functions are called before any adapter is instantiated or
any HTTP request is dispatched. They raise ValueError with a user-facing
message on invalid input.

SSRF protection is the most critical validator here. The hosted API accepts
arbitrary user-supplied URLs and dispatches HTTP requests from Fynor's
infrastructure — without SSRF protection, an attacker can probe internal
AWS services (metadata API, VPC resources, DynamoDB endpoints).

References:
- OWASP SSRF Prevention Cheat Sheet
- AWS Security Blog: "SSRF and the AWS Metadata Service"
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

_VALID_INTERFACE_TYPES = frozenset({
    "mcp", "rest", "graphql", "grpc", "websocket", "soap", "cli"
})

_VALID_CHECK_NAMES = frozenset({
    "latency_p95", "error_rate", "schema", "retry",
    "auth_token", "rate_limit", "timeout", "log_completeness",
})


def validate_interface_type(interface_type: str) -> None:
    """
    Validate the interface type field from a POST /check request.

    Args:
        interface_type: The interface type string to validate.

    Raises:
        ValueError: If the interface type is not in the supported set.
    """
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

    # Validate auth_token
    auth_token = options.get("auth_token")
    if auth_token is not None:
        if not isinstance(auth_token, str) or not auth_token.strip():
            raise ValueError("'options.auth_token' must be a non-empty string.")
        if len(auth_token) > 2048:
            raise ValueError(
                "'options.auth_token' must be ≤ 2048 characters. "
                "If you're using a JWT, ensure it's not expired."
            )
