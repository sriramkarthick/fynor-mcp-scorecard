"""
fynor/checks/mcp/data_freshness.py — Check #9: data_freshness

Verifies the MCP server includes a detectable recency timestamp in its response
and that the data is within an acceptable freshness window.

Scoring (step function — no interpolation):
  No detectable timestamp in response       → score = 0
  Timestamp present, data age > 24h        → score = 20
  Timestamp present, data age ≤ 24h        → score = 60  ← pass threshold
  Timestamp present, data age ≤ 60 min     → score = 80
  Timestamp present, data age ≤ 5 min      → score = 100

ADR-03 signal class: Reliability — data currency
Pass threshold: score ≥ 60 (data age ≤ 24 hours)

result.value: data age in minutes (float), or None if no timestamp found.
result.detail: human-readable explanation including detected timestamp field name.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fynor.adapters.base import BaseAdapter
from fynor.checks.shared import _TIMESTAMP_KEYS, find_timestamp as _find_timestamp
from fynor.checks.shared import parse_timestamp as _parse_timestamp
from fynor.history import CheckResult

CHECK_NAME = "data_freshness"

_FRESH_5MIN = 5.0
_FRESH_60MIN = 60.0
_FRESH_24H = 24 * 60.0


def _score_from_age_minutes(age_minutes: float) -> int:
    if age_minutes <= _FRESH_5MIN:
        return 100
    if age_minutes <= _FRESH_60MIN:
        return 80
    if age_minutes <= _FRESH_24H:
        return 60
    return 20


async def check_data_freshness(adapter: BaseAdapter) -> CheckResult:
    """Send one probe and assess the recency of data in the response."""
    try:
        response = await adapter.call()
    except Exception as exc:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=None,
            detail=f"Probe failed: {exc}",
            evidence={"error": str(exc)},
        )

    body = response.body
    if not body:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=None,
            detail="Empty response body — cannot assess data freshness.",
            evidence={"response_status": response.status_code, "body_empty": True},
        )

    field_name, raw_value = _find_timestamp(body)
    if field_name is None:
        # Show the actual top-level keys the server returned — proves we really looked
        top_keys = list(body.keys())[:15] if isinstance(body, dict) else []
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=None,
            detail=(
                "No timestamp field detected in response. "
                "MCP servers should include a recency indicator (e.g. 'timestamp', "
                "'updated_at') so agents can assess data currency."
            ),
            evidence={
                "response_status": response.status_code,
                # The actual field names returned by this server — shows we searched them
                "fields_found_in_response": top_keys,
                "timestamp_keys_searched": sorted(_TIMESTAMP_KEYS),
            },
        )

    if raw_value is None:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=None,
            detail=f"Timestamp field '{field_name}' found but value is null.",
            evidence={
                "timestamp_field_found": field_name,
                "timestamp_raw_value": None,
                "parse_error": "null value",
            },
        )

    parsed_dt = _parse_timestamp(raw_value)
    if parsed_dt is None:
        return CheckResult(
            check=CHECK_NAME, passed=False, score=0, value=None,
            detail=(
                f"Timestamp field '{field_name}' found but value '{raw_value[:40]}' "
                "could not be parsed. Use ISO 8601 or Unix epoch format."
            ),
            evidence={
                "timestamp_field_found": field_name,
                # The actual raw value from this server's response
                "timestamp_raw_value": raw_value[:80],
                "parse_error": "unrecognised format",
            },
        )

    now = datetime.now(tz=timezone.utc)
    age_minutes = (now - parsed_dt).total_seconds() / 60.0
    if age_minutes < 0:
        age_minutes = 0.0

    score = _score_from_age_minutes(age_minutes)
    passed = score >= 60

    if age_minutes < 1.0:
        age_str = f"{age_minutes * 60:.0f}s"
    elif age_minutes < 60.0:
        age_str = f"{age_minutes:.1f}min"
    else:
        age_str = f"{age_minutes / 60:.1f}h"

    if age_minutes > _FRESH_24H:
        freshness_note = "Stale — agents may reason over outdated data."
    elif age_minutes <= _FRESH_5MIN:
        freshness_note = "Fresh."
    else:
        freshness_note = "Acceptable."

    detail = (
        f"Data age: {age_str} (field: '{field_name}'). "
        f"Pass threshold: ≤24h. {freshness_note}"
    )

    return CheckResult(
        check=CHECK_NAME, passed=passed, score=score,
        value=round(age_minutes, 2), detail=detail,
        evidence={
            "response_status": response.status_code,
            # The exact field name and raw value found in this server's response
            "timestamp_field_found": field_name,
            "timestamp_raw_value": raw_value[:80],
            "timestamp_parsed_utc": parsed_dt.isoformat(),
            "data_age_minutes": round(age_minutes, 2),
            "data_age_human": age_str,
            "freshness_bands": {
                "pass_threshold_minutes": _FRESH_24H,
                "excellent_threshold_minutes": _FRESH_5MIN,
            },
        },
    )
