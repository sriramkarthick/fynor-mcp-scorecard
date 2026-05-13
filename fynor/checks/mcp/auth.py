"""
fynor.checks.mcp.auth — Check 5: Auth token handling.

Tests three failure modes agents encounter in production:
  1. Server leaks credentials in response headers
  2. Server accepts requests with no auth (should return 401)
  3. Server accepts hardcoded secrets in URL parameters

ADR-02: auth_token is a security check (weight 30%).
A score of 0 on this check caps the overall grade at D.

Pass: all three sub-checks pass.
Score:
  All pass  → 100
  1 failure →  40
  2 failures→  10
  All fail  →   0
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

from fynor.adapters.base import BaseAdapter
from fynor.adapters.mcp import MCPAdapter
from fynor.history import CheckResult

# Patterns that indicate credential leakage in response headers
_SECRET_HEADER_PATTERNS = re.compile(
    r"(authorization|x-auth-token|x-api-key|x-secret|bearer|token|secret|password)",
    re.IGNORECASE,
)

# URL query param names that should never carry secrets
_SECRET_PARAM_NAMES = re.compile(
    r"(api[_-]?key|token|secret|password|auth|credential)",
    re.IGNORECASE,
)


def check_auth_token(adapter: BaseAdapter) -> CheckResult:
    """
    Verify correct auth token handling across three sub-checks.

    Sub-check 1: No credential leakage in response headers.
    Sub-check 2: Unauthenticated request returns 401 (not 200).
    Sub-check 3: No secrets embedded in the target URL's query parameters.

    Returns:
        CheckResult with check="auth_token".
    """
    failures: list[str] = []

    # Sub-check 1: credential leakage in response headers
    response = adapter.call()
    leaked_headers = [
        h for h in response.headers
        if _SECRET_HEADER_PATTERNS.search(h)
        and h.lower() not in ("authorization",)  # authorization in request is ok
    ]
    if leaked_headers:
        failures.append(
            f"Credential leakage: response headers contain {leaked_headers}."
        )

    # Sub-check 2: unauthenticated request should return 401
    if isinstance(adapter, MCPAdapter):
        unauth_response = adapter.call_without_auth()
        if unauth_response.status_code == 200:
            failures.append(
                "Unauthenticated request returned 200 — "
                "server does not enforce authentication."
            )
        elif unauth_response.status_code not in (401, 403):
            failures.append(
                f"Unauthenticated request returned {unauth_response.status_code} "
                f"(expected 401 or 403)."
            )

    # Sub-check 3: no secrets in URL query parameters
    parsed = urlparse(adapter.target)
    params = parse_qs(parsed.query)
    secret_params = [p for p in params if _SECRET_PARAM_NAMES.search(p)]
    if secret_params:
        failures.append(
            f"Secrets in URL parameters: {secret_params}. "
            "URL parameters are visible in server logs and browser history."
        )

    passed = len(failures) == 0
    score = _score_from_failures(len(failures))

    if passed:
        detail = "Auth token handling is correct: no leakage, 401 on missing auth, no URL secrets."
    else:
        detail = " | ".join(failures)

    return CheckResult(
        check="auth_token",
        passed=passed,
        score=score,
        value=len(failures),
        detail=detail,
    )


def _score_from_failures(n: int) -> int:
    return {0: 100, 1: 40, 2: 10}.get(n, 0)
