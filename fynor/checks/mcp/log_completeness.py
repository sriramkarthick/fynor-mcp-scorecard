"""
fynor.checks.mcp.log_completeness — Check 8: Audit log exposure.

Probes common log endpoints (/logs, /audit, /events) and verifies the
server exposes a structured, queryable audit trail with timestamps.
Agents in regulated environments (FinTech, healthcare) require complete
audit logs — a server with no structured logs fails compliance silently.

Pass: a log endpoint returns structured JSON with at least one timestamp field.
Score:
  Structured JSON + timestamps  → 100   (queryable, compliant)
  Structured JSON, no timestamps →  70   (queryable, incomplete)
  Plain text logs               →  40   (exists but not machine-queryable)
  No log endpoint found         →   0   (no audit trail)
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from fynor.adapters.base import BaseAdapter
from fynor.history import CheckResult

_LOG_PATHS = ["/logs", "/audit", "/audit-log", "/events", "/_logs", "/v1/logs"]
_TIMESTAMP_KEYS = {"timestamp", "ts", "created_at", "time", "datetime", "logged_at"}


def check_log_completeness(adapter: BaseAdapter) -> CheckResult:
    """
    Probe known log endpoint paths and assess log structure.

    Returns:
        CheckResult with check="log_completeness", value=path_found_or_None.
    """
    parsed = urlparse(adapter.target)
    root = f"{parsed.scheme}://{parsed.netloc}"

    found_path: str | None = None
    body: dict | list | str | None = None

    client = httpx.Client(timeout=5.0)
    try:
        for path in _LOG_PATHS:
            try:
                r = client.get(f"{root}{path}")
                if r.status_code == 200:
                    found_path = path
                    try:
                        body = r.json()
                    except Exception:  # noqa: BLE001
                        body = r.text
                    break
            except Exception:  # noqa: BLE001
                continue
    finally:
        client.close()

    if found_path is None:
        return CheckResult(
            check="log_completeness",
            passed=False,
            score=0,
            value=None,
            detail=(
                f"No audit log endpoint found at: {', '.join(_LOG_PATHS)}. "
                "Agents in regulated environments require structured audit trails. "
                "Add a /logs or /audit endpoint returning structured JSON."
            ),
        )

    if isinstance(body, (dict, list)):
        body_keys = _extract_keys(body)
        has_timestamps = bool(body_keys & _TIMESTAMP_KEYS)

        if has_timestamps:
            return CheckResult(
                check="log_completeness",
                passed=True,
                score=100,
                value=found_path,
                detail=(
                    f"Structured JSON audit log with timestamps found at {found_path}. "
                    "Fully queryable by agents and compliant with audit requirements."
                ),
            )

        return CheckResult(
            check="log_completeness",
            passed=True,
            score=70,
            value=found_path,
            detail=(
                f"Structured JSON log found at {found_path} "
                f"but no timestamp fields detected (looked for: {sorted(_TIMESTAMP_KEYS)}). "
                "Add a timestamp field to enable time-range queries."
            ),
        )

    return CheckResult(
        check="log_completeness",
        passed=False,
        score=40,
        value=found_path,
        detail=(
            f"Log endpoint {found_path} returns plain text — not machine-queryable. "
            "Return structured JSON so agents can filter by time, severity, and event type."
        ),
    )


def _extract_keys(body: dict | list) -> set[str]:
    """Recursively collect all dict keys from a JSON body."""
    keys: set[str] = set()
    if isinstance(body, dict):
        keys.update(k.lower() for k in body)
        for v in body.values():
            if isinstance(v, (dict, list)):
                keys |= _extract_keys(v)
    elif isinstance(body, list):
        for item in body[:5]:  # sample first 5 items
            if isinstance(item, (dict, list)):
                keys |= _extract_keys(item)
    return keys
