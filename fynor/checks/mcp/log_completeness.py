"""
fynor.checks.mcp.log_completeness — Check 8: Audit log exposure.

Probes standard observability paths and verifies the server exposes a
structured, queryable audit trail. Agents in regulated environments
(FinTech, healthcare, legal) require complete audit logs — a server with
no structured logs fails compliance silently.

Probe paths (in order):
  Log-specific:  /logs, /audit, /audit-log, /events, /v1/logs
  Observability: /metrics, /health, /.well-known/health, /status

Scoring:
  Structured JSON + timestamp fields   → 100   (pass — queryable, compliant)
  Structured JSON, no timestamp fields →  70   (pass — queryable, add timestamps)
  Plain text logs accessible           →  60   (pass — exists but not machine-queryable)
  Health / status endpoint only        →  40   (fail — no log data, only liveness)
  No log endpoint found                →   0   (fail — no audit trail)

Pass threshold: score ≥ 60 (any log endpoint exists).
A health-only endpoint (40) is a FAIL because it provides no audit capability.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

# Log-specific paths — probed first; a match here scores higher
_LOG_PATHS = ["/logs", "/audit", "/audit-log", "/events", "/v1/logs"]
# Observability fallback paths — a match here scores 40 (health/status only)
_HEALTH_PATHS = ["/metrics", "/health", "/.well-known/health", "/status"]

_TIMESTAMP_KEYS = frozenset({
    "timestamp", "ts", "created_at", "time", "datetime", "logged_at",
    "event_time", "occurred_at", "recorded_at",
})

_IMPL_GUIDE = (
    "To pass: expose a /logs or /audit endpoint returning JSON with at least one "
    "timestamp field (e.g. {'ts': ..., 'level': ..., 'message': ...}). "
    "See fynor.tech/docs/observability for a minimal implementation guide."
)


async def check_log_completeness(adapter: BaseAdapter) -> CheckResult:
    """
    Probe known log and observability paths, assess log structure.

    Returns:
        CheckResult with check="log_completeness", value=path_found_or_None.
    """
    parsed = urlparse(adapter.target)
    root = f"{parsed.scheme}://{parsed.netloc}"

    all_probed = _LOG_PATHS + _HEALTH_PATHS

    # Try log-specific paths first (higher value)
    log_result = await _probe_paths(root, _LOG_PATHS)
    if log_result is not None:
        found_path, body = log_result
        return _score_log_body(found_path, body, all_probed)

    # Fall back to health/status paths (lower value — liveness, not audit)
    health_result = await _probe_paths(root, _HEALTH_PATHS)
    if health_result is not None:
        found_path, health_body = health_result
        return CheckResult(
            check="log_completeness",
            passed=False,
            score=40,
            value=found_path,
            detail=(
                f"Only a health/liveness endpoint was found at {found_path!r} — "
                "this confirms the server is alive but provides no audit capability. "
                f"{_IMPL_GUIDE}"
            ),
            evidence={
                "paths_probed": all_probed,
                "found_path": found_path,
                "found_type": "health/liveness",
                # Preview of what the health endpoint actually returned
                "response_preview": str(health_body)[:200],
            },
        )

    return CheckResult(
        check="log_completeness",
        passed=False,
        score=0,
        value=None,
        detail=(
            f"No observability endpoint found at: {', '.join(all_probed)}. "
            "Agents in regulated environments cannot operate without an audit trail. "
            f"{_IMPL_GUIDE}"
        ),
        evidence={
            "paths_probed": all_probed,
            "found_path": None,
        },
    )


async def _probe_paths(
    root: str, paths: list[str]
) -> tuple[str, dict[str, Any] | list[Any] | str] | None:
    """
    Probe each path in order; return (path, body) for the first 200 response.
    Returns None if no path responds with 200.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        for path in paths:
            try:
                r = await client.get(f"{root}{path}")
                if r.status_code == 200:
                    try:
                        body: dict[str, Any] | list[Any] | str = r.json()
                    except Exception:  # noqa: BLE001
                        body = r.text
                    return path, body
            except Exception:  # noqa: BLE001
                continue
    return None


def _score_log_body(
    found_path: str, body: dict[str, Any] | list[Any] | str, all_probed: list[str] | None = None
) -> CheckResult:
    """Score a found log endpoint based on its response structure."""
    body_preview = str(body)[:300]
    paths_ev: list[str] = all_probed if all_probed is not None else []

    if not isinstance(body, (dict, list)):
        # Plain text — log exists but is not machine-queryable
        return CheckResult(
            check="log_completeness",
            passed=True,
            score=60,
            value=found_path,
            detail=(
                f"Plain-text log endpoint found at {found_path!r}. "
                "Logs exist but are not machine-queryable — agents cannot filter "
                "by time, severity, or event type. "
                "Return JSON (e.g. [{\"ts\": ..., \"level\": ..., \"msg\": ...}]) "
                "for full agent compatibility."
            ),
            evidence={
                "paths_probed": all_probed,
                "found_path": found_path,
                "response_format": "plain-text",
                "response_preview": body_preview,
            },
        )

    body_keys = _extract_keys(body)
    has_timestamps = bool(body_keys & _TIMESTAMP_KEYS)
    matched_ts_keys = sorted(body_keys & _TIMESTAMP_KEYS)

    if has_timestamps:
        return CheckResult(
            check="log_completeness",
            passed=True,
            score=100,
            value=found_path,
            detail=(
                f"Structured JSON audit log with timestamp fields found at {found_path!r}. "
                "Fully queryable by agents and compliant with audit requirements."
            ),
            evidence={
                "paths_probed": all_probed,
                "found_path": found_path,
                "response_format": "json",
                # The actual timestamp field names found in this server's response
                "timestamp_fields_found": matched_ts_keys,
                "all_fields_found": sorted(body_keys)[:20],
                "response_preview": body_preview,
            },
        )

    return CheckResult(
        check="log_completeness",
        passed=True,
        score=70,
        value=found_path,
        detail=(
            f"Structured JSON log found at {found_path!r} but no timestamp fields detected. "
            f"Expected one of: {sorted(_TIMESTAMP_KEYS)[:5]}... "
            "Add a timestamp field to enable time-range queries by agents and auditors."
        ),
        evidence={
            "paths_probed": all_probed,
            "found_path": found_path,
            "response_format": "json",
            "timestamp_fields_found": [],
            # Actual field names returned by this server — shows exactly what's there
            "all_fields_found": sorted(body_keys)[:20],
            "response_preview": body_preview,
        },
    )


def _extract_keys(body: dict[str, Any] | list[Any]) -> set[str]:
    """Recursively collect all dict keys from a JSON body (sample first 5 items)."""
    keys: set[str] = set()
    if isinstance(body, dict):
        keys.update(k.lower() for k in body)
        for v in body.values():
            if isinstance(v, (dict, list)):
                keys |= _extract_keys(v)
    elif isinstance(body, list):
        for item in body[:5]:
            if isinstance(item, (dict, list)):
                keys |= _extract_keys(item)
    return keys
