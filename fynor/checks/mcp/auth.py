"""
fynor.checks.mcp.auth — Check 5: Auth token handling.

Tests four failure modes agents encounter in production:
  1. Server leaks credentials in response headers.
  2. Server accepts unauthenticated requests (should return 401 or 403).
  3. Server accepts hardcoded secrets in URL parameters.
  4. Server accepts a syntactically invalid Bearer token (token signature not validated).

ADR-02: auth_token is a security check (weight 30%).
A score of 0 on this check caps the overall grade at D regardless of
all other scores. This is the only check that can trigger the security cap.

IMPORTANT: secret values are NEVER logged. Only the header/param NAME is
recorded in the detail field. This constraint is non-negotiable.

Scoring:
  All sub-checks pass  → 100
  1 failure            →  40
  2 failures           →  10
  3+ failures          →   0
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx

from fynor.adapters.base import BaseAdapter
from fynor.adapters.mcp import MCPAdapter
from fynor.history import CheckResult

# Header names that indicate credential leakage in responses.
# These patterns are intentionally conservative — false negatives here are
# worse than false positives (a missed leak is a real vulnerability).
_SECRET_HEADER_PATTERNS = re.compile(
    r"(x-auth-token|x-api-key|x-secret|x-token|x-access-token|"
    r"x-refresh-token|x-session|x-password|api-key|secret|password)",
    re.IGNORECASE,
)

# URL query parameter names that should never carry secrets.
# API keys in URLs appear in server logs, browser history, and CDN logs.
_SECRET_PARAM_NAMES = re.compile(
    r"(api[_-]?key|token|secret|password|auth|credential|access[_-]?key)",
    re.IGNORECASE,
)

# A syntactically plausible but semantically invalid Bearer token.
# Used in F4 to test whether the server validates token signatures or
# only checks token presence/format.
_FAKE_BEARER_TOKEN = "fynor.reliability.checker.invalid.token.v1"

# MCP probe payload used for the fake-token sub-check (same as the standard probe).
_PROBE_PAYLOAD = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


async def check_auth_token(adapter: BaseAdapter) -> CheckResult:
    """
    Verify correct auth token handling across three sub-checks.

    Sub-check 1: No credential leakage in response headers.
                 Inspects all response header names for credential patterns.
                 Values are NEVER logged.

    Sub-check 2: Unauthenticated request returns 401 or 403, not 200.
                 Only runs for MCPAdapter (requires call_without_auth()).

    Sub-check 3: No secrets embedded in the target URL query parameters.
                 URL params are visible in server logs and browser history.

    Returns:
        CheckResult with check="auth_token".
    """
    failures: list[str] = []

    # Evidence dict: carries actual data from this client's server.
    # Values here are real HTTP responses, not templates.
    # Constraint (unchanged): secret VALUES are never recorded — only header/param NAMES.
    ev: dict[str, object] = {
        "probe_token_used": _FAKE_BEARER_TOKEN,  # the exact token we sent
    }

    # Sub-check 1: credential leakage in response headers
    response = await adapter.call()
    ev["f1_response_status"] = response.status_code
    ev["f1_response_headers_checked"] = list(response.headers.keys())
    leaked_headers = [
        h for h in response.headers
        if _SECRET_HEADER_PATTERNS.search(h)
    ]
    ev["f1_leaked_header_names"] = leaked_headers  # names only, never values
    if leaked_headers:
        # Log header NAMES only — never the values.
        failures.append(
            f"Response exposes credential-pattern headers: {leaked_headers}. "
            "Agents capture and forward all response headers — credential leakage "
            "propagates through the pipeline. Remove these headers from responses."
        )

    # Sub-check 2: unauthenticated request should be rejected
    f2_fired = False
    ev["f2_ran"] = isinstance(adapter, MCPAdapter)
    if isinstance(adapter, MCPAdapter):
        unauth = await adapter.call_without_auth()
        ev["f2_unauth_status"] = unauth.status_code
        # Capture first 200 chars of unauthenticated response body (no secrets — this
        # is the response to a request with no credentials at all).
        _f2_body = unauth.body
        _f2_preview = (
            str(_f2_body)[:200] if _f2_body is not None else ""
        )
        ev["f2_response_preview"] = _f2_preview
        if unauth.status_code == 200:
            f2_fired = True
            failures.append(
                "Unauthenticated request returned HTTP 200 — server accepts requests "
                "without credentials. Add authentication enforcement and return 401."
            )
        elif unauth.status_code not in (401, 403):
            failures.append(
                f"Unauthenticated request returned HTTP {unauth.status_code} "
                f"(expected 401 or 403). Ambiguous status prevents agents from "
                f"detecting auth failures reliably."
            )

    # Sub-check 3: no secrets in URL query parameters
    parsed = urlparse(adapter.target)
    params = parse_qs(parsed.query)
    secret_params = [p for p in params if _SECRET_PARAM_NAMES.search(p)]
    ev["f3_secret_param_names"] = secret_params  # param names only, never values
    if secret_params:
        failures.append(
            f"Secrets in URL query parameters: {secret_params}. "
            "URL parameters appear in server access logs, CDN logs, and browser history. "
            "Pass credentials via Authorization header instead."
        )

    # Sub-check 4: fake/invalid token accepted — only meaningful if F2 did NOT fire.
    # F2 fires when the server accepts unauthenticated requests; in that case,
    # the server trivially accepts any token, so running F4 would double-count.
    ev["f4_ran"] = isinstance(adapter, MCPAdapter) and not f2_fired
    if isinstance(adapter, MCPAdapter) and not f2_fired:
        try:
            async with httpx.AsyncClient(timeout=10.0) as _client:
                _fake_resp = await _client.post(
                    adapter.target,
                    json=_PROBE_PAYLOAD,
                    headers={
                        "Authorization": f"Bearer {_FAKE_BEARER_TOKEN}",
                        "Content-Type": "application/json",
                        "User-Agent": "Fynor-Reliability-Checker/1.0",
                    },
                )
            ev["f4_response_status"] = _fake_resp.status_code
            # Capture first 300 chars of the actual response body from this specific server.
            # This is the proof: what their server returned when we sent a fake token.
            ev["f4_response_preview"] = (_fake_resp.text or "")[:300]
            ev["f4_response_content_type"] = _fake_resp.headers.get("content-type", "")
            if _fake_resp.status_code == 200:
                failures.append(
                    "Server accepted a syntactically invalid token (HTTP 200). "
                    "Token signature validation is not enforced — any bearer token "
                    "is accepted. Implement proper token signature verification."
                )
        except Exception:
            # Network error on this sub-check is not a failure — skip gracefully.
            ev["f4_ran"] = False

    passed = len(failures) == 0
    score = _score_from_failures(len(failures))

    if passed:
        detail = (
            "Auth token handling is correct: no header leakage, "
            "unauthenticated requests rejected, no secrets in URL."
        )
    else:
        detail = " | ".join(failures)
        # Truncate to 500 chars to fit storage constraints without losing structure
        if len(detail) > 500:
            detail = detail[:497] + "..."

    return CheckResult(
        check="auth_token",
        passed=passed,
        score=score,
        value=len(failures),
        detail=detail,
        evidence=ev,
    )


def _score_from_failures(n: int) -> int:
    """Map failure count to score. Locked — any change requires ADR-02 amendment.
    With 4 possible failure conditions, n=4 maps to 0 via the default fallback.
    """
    return {0: 100, 1: 40, 2: 10, 3: 0}.get(n, 0)
