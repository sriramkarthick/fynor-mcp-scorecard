"""
fynor/checks/shared.py — Shared utilities used across multiple check types.

Decision D6 (plan-eng-review 2026-05-15): Extract duplicated logic from
individual check modules into this shared module so each adapter's
response_determinism and data_freshness checks import from one place.

Public API
----------
compare_responses(r1, r2) -> bool
    Deep structural + value comparison of two response bodies.
    Returns True iff the two bodies are identical.
    Used by the response_determinism check across all adapter types.

extract_timestamp(body, header_map, field_paths=None) -> datetime | None
    Locate a freshness timestamp in a response body or fallback headers.
    field_paths: explicit ordered list of dot-separated key paths to try
    first (e.g. ["meta.ts", "ts"]).  When a path misses, or when
    field_paths is None, falls back to auto-scanning for known timestamp
    field names recursively.  When the body yields nothing, tries common
    HTTP headers (Last-Modified, Date) from header_map.
    Returns a timezone-aware UTC datetime, or None if nothing found.

Internal helpers (exported for direct use by existing check modules)
--------------------------------------------------------------------
key_fingerprint(obj, depth=0) -> str
find_timestamp(obj, depth=0) -> tuple[str | None, str | None]
parse_timestamp(raw) -> datetime | None
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

# ---------------------------------------------------------------------------
# Timestamp field names considered "freshness indicators"
# ---------------------------------------------------------------------------

_TIMESTAMP_KEYS: frozenset[str] = frozenset({
    "timestamp", "ts", "time", "datetime", "created_at", "logged_at",
    "event_time", "occurred_at", "recorded_at", "updated_at", "modified_at",
    "generated_at", "fetched_at", "collected_at", "observed_at",
})

# HTTP response headers consulted as a last-resort freshness fallback.
_FRESHNESS_HEADERS: tuple[str, ...] = ("last-modified", "date")


# ---------------------------------------------------------------------------
# key_fingerprint — structural fingerprint (keys + types, NOT values)
# ---------------------------------------------------------------------------

def key_fingerprint(obj: Any, depth: int = 0) -> str:
    """Canonical structural fingerprint of an object (keys + types, not values).

    Identical to the former ``_key_fingerprint`` in
    ``fynor/checks/mcp/response_determinism.py``.  Exported from here so all
    adapter-specific response_determinism modules share one implementation.
    """
    if depth > 3:
        return type(obj).__name__
    if isinstance(obj, dict):
        parts = sorted(
            f"{k}:{key_fingerprint(v, depth + 1)}" for k, v in obj.items()
        )
        return "{" + ",".join(parts) + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        return f"[{key_fingerprint(obj[0], depth + 1)}]"
    return type(obj).__name__


# ---------------------------------------------------------------------------
# find_timestamp — recursive body scan for known freshness fields
# ---------------------------------------------------------------------------

def find_timestamp(obj: Any, depth: int = 0) -> tuple[str | None, str | None]:
    """Recursively search *obj* for a timestamp field.

    Returns ``(field_name, raw_value)`` where *raw_value* is a string
    suitable for ``parse_timestamp``, or ``(None, None)`` if not found.

    Identical to the former ``_find_timestamp`` in
    ``fynor/checks/mcp/data_freshness.py``.
    """
    if depth > 4:
        return None, None
    if isinstance(obj, dict):
        for key, value in obj.items():
            if any(ts_key in key.lower() for ts_key in _TIMESTAMP_KEYS):
                if isinstance(value, (str, int, float)):
                    return key, str(value)
            found_key, found_val = find_timestamp(value, depth + 1)
            if found_key is not None:
                return found_key, found_val
    elif isinstance(obj, list) and len(obj) > 0:
        return find_timestamp(obj[0], depth + 1)
    return None, None


# ---------------------------------------------------------------------------
# parse_timestamp — parse a raw string/numeric value into a datetime
# ---------------------------------------------------------------------------

def parse_timestamp(raw: str) -> datetime | None:
    """Parse a timestamp string or numeric epoch value.

    Handles:
    * Float / int Unix epoch seconds (> 1e12 treated as milliseconds).
    * ISO 8601 variants with and without timezone suffix.

    Returns a timezone-aware UTC datetime, or None on parse failure.

    Identical to the former ``_parse_timestamp`` in
    ``fynor/checks/mcp/data_freshness.py``.
    """
    # --- numeric epoch ---
    try:
        val = float(raw)
        if val > 1e12:
            val /= 1000.0
        return datetime.fromtimestamp(val, tz=timezone.utc)
    except (ValueError, OSError):
        pass

    # --- ISO 8601 string variants ---
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


# ---------------------------------------------------------------------------
# _resolve_field_path — navigate "meta.ts" dotted paths in a dict
# ---------------------------------------------------------------------------

def _resolve_field_path(obj: Any, path: str) -> str | None:
    """Walk *obj* by the dot-separated *path* and return the raw string value.

    Returns None if any segment is missing or the value is not a
    scalar (str / int / float).
    """
    parts = path.split(".")
    current: Any = obj
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, (str, int, float)):
        return str(current)
    return None


# ---------------------------------------------------------------------------
# Public high-level API
# ---------------------------------------------------------------------------

def compare_responses(r1: Any, r2: Any) -> bool:
    """Return True iff *r1* and *r2* are identical.

    Performs a plain equality comparison.  Both the structure AND the values
    must match.  The response_determinism check uses this to decide whether
    consecutive probes returned the same result; a timestamp-only difference
    (e.g. ``"ts": "2026-01-01"`` vs ``"ts": "2026-01-02"``) is intentionally
    treated as *not equal* so the check can detect non-deterministic servers.

    Returns a strict ``bool`` (not just a truthy/falsy value).
    """
    return bool(r1 == r2)


def extract_timestamp(
    body: Any,
    header_map: dict[str, str],
    field_paths: list[str] | None = None,
) -> datetime | None:
    """Locate a freshness timestamp and return a timezone-aware UTC datetime.

    Resolution order
    ~~~~~~~~~~~~~~~~
    1. Explicit *field_paths* (dot-separated, tried in order).
    2. Auto-scan *body* for known timestamp field names (recursive).
    3. HTTP headers in *header_map* (``Last-Modified``, then ``Date``).

    When a field_paths entry misses, scanning continues to the next entry
    and then falls back to auto-scan — paths are hints, not requirements.

    Returns None if no parseable timestamp is found anywhere.
    """
    # --- 1. explicit field paths ---
    if field_paths:
        for path in field_paths:
            raw = _resolve_field_path(body, path)
            if raw is not None:
                dt = parse_timestamp(raw)
                if dt is not None:
                    return dt

    # --- 2. auto-scan body ---
    _, raw_body = find_timestamp(body)
    if raw_body is not None:
        dt = parse_timestamp(raw_body)
        if dt is not None:
            return dt

    # --- 3. header fallback ---
    for header_name in _FRESHNESS_HEADERS:
        raw_header = header_map.get(header_name) or header_map.get(header_name.title())
        if raw_header:
            # Try RFC 7231 HTTP-date format first (Last-Modified / Date)
            try:
                dt = parsedate_to_datetime(raw_header)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
            # Fallback: try ISO 8601 parse
            dt = parse_timestamp(raw_header)
            if dt is not None:
                return dt

    return None
