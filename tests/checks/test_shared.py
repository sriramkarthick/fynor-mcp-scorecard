"""
tests/checks/test_shared.py — Unit tests for fynor.checks.shared.

T11a (plan-eng-review 2026-05-15): tests written FIRST (decision D8) before
implementing fynor/checks/shared.py.

Decision D6: extract compare_responses() and extract_timestamp() into shared.py
so each adapter's response_determinism and data_freshness checks import from one
place instead of duplicating the logic 5+ times.

compare_responses(r1, r2) -> bool
  Deep structural+value comparison of two response bodies.
  Used by the response_determinism check across all adapter types.

extract_timestamp(body, header_map, field_paths) -> datetime | None
  Locate a timestamp in a response body or headers.
  Used by the data_freshness check across all adapter types.
  field_paths: explicit list of key paths to try first (e.g. ["meta.ts", "ts"]).
  Falls back to scanning common timestamp field names when field_paths is None.
  Falls back to header_map when body yields nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from fynor.checks.shared import compare_responses, extract_timestamp


# ===========================================================================
# compare_responses
# ===========================================================================

class TestCompareResponses:

    # -- identical inputs ----------------------------------------------------

    def test_identical_dict_returns_true(self):
        r = {"status": "ok", "code": 200}
        assert compare_responses(r, r.copy()) is True

    def test_identical_string_returns_true(self):
        assert compare_responses("hello", "hello") is True

    def test_identical_empty_dict_returns_true(self):
        assert compare_responses({}, {}) is True

    def test_identical_empty_string_returns_true(self):
        assert compare_responses("", "") is True

    def test_identical_none_returns_true(self):
        assert compare_responses(None, None) is True

    def test_identical_list_returns_true(self):
        assert compare_responses([1, 2, 3], [1, 2, 3]) is True

    def test_identical_nested_dict_returns_true(self):
        r = {"data": {"items": [{"id": 1}]}, "count": 1}
        assert compare_responses(r, {"data": {"items": [{"id": 1}]}, "count": 1}) is True

    def test_non_json_xml_identical_returns_true(self):
        """Non-JSON text (e.g. SOAP/XML) — identical strings are equal."""
        xml = "<response><status>ok</status></response>"
        assert compare_responses(xml, xml) is True

    # -- different values ----------------------------------------------------

    def test_different_field_value_returns_false(self):
        r1 = {"status": "ok"}
        r2 = {"status": "error"}
        assert compare_responses(r1, r2) is False

    def test_extra_field_in_r2_returns_false(self):
        r1 = {"status": "ok"}
        r2 = {"status": "ok", "extra": "field"}
        assert compare_responses(r1, r2) is False

    def test_missing_field_in_r2_returns_false(self):
        r1 = {"status": "ok", "code": 200}
        r2 = {"status": "ok"}
        assert compare_responses(r1, r2) is False

    def test_empty_vs_nonempty_returns_false(self):
        assert compare_responses({}, {"a": 1}) is False

    def test_empty_string_vs_nonempty_string_returns_false(self):
        assert compare_responses("", "data") is False

    def test_different_types_returns_false(self):
        """Dict vs string — different types → False."""
        assert compare_responses({"a": 1}, '{"a": 1}') is False

    def test_none_vs_empty_dict_returns_false(self):
        assert compare_responses(None, {}) is False

    def test_nested_value_change_returns_false(self):
        r1 = {"data": {"count": 1}}
        r2 = {"data": {"count": 2}}
        assert compare_responses(r1, r2) is False

    def test_list_order_matters(self):
        """Lists are ordered — [1,2] != [2,1]."""
        assert compare_responses([1, 2], [2, 1]) is False

    def test_list_length_matters(self):
        assert compare_responses([1, 2], [1, 2, 3]) is False

    # -- return type ---------------------------------------------------------

    def test_returns_bool_not_truthy(self):
        result = compare_responses({"a": 1}, {"a": 1})
        assert result is True          # strict bool, not just truthy

    def test_returns_bool_false_not_falsy(self):
        result = compare_responses({"a": 1}, {"a": 2})
        assert result is False         # strict bool, not just falsy


# ===========================================================================
# extract_timestamp
# ===========================================================================

class TestExtractTimestamp:

    # -- ISO 8601 in body ----------------------------------------------------

    def test_iso8601_utc_in_body_field(self):
        body = {"updated_at": "2026-01-15T10:30:00Z"}
        dt = extract_timestamp(body, {})
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 15

    def test_iso8601_with_timezone_offset(self):
        body = {"timestamp": "2026-03-01T12:00:00+05:30"}
        dt = extract_timestamp(body, {})
        assert dt is not None
        # Normalised to UTC: 12:00 +5:30 = 06:30 UTC
        assert dt.tzinfo is not None

    def test_iso8601_with_microseconds(self):
        body = {"created_at": "2026-05-15T09:23:45.123456Z"}
        dt = extract_timestamp(body, {})
        assert dt is not None

    # -- Unix epoch in body --------------------------------------------------

    def test_unix_epoch_seconds(self):
        body = {"ts": 1700000000}
        dt = extract_timestamp(body, {})
        assert dt is not None
        assert dt.year == 2023   # 2023-11-14

    def test_unix_epoch_milliseconds(self):
        """Epoch > 1e12 → treated as milliseconds, divided by 1000."""
        body = {"ts": 1700000000000}   # milliseconds
        dt = extract_timestamp(body, {})
        assert dt is not None
        assert dt.year == 2023

    def test_unix_epoch_as_float(self):
        body = {"timestamp": 1700000000.5}
        dt = extract_timestamp(body, {})
        assert dt is not None

    # -- Nested fields -------------------------------------------------------

    def test_nested_field_path(self):
        """field_paths=['meta.ts'] navigates nested dict."""
        body = {"meta": {"ts": "2026-01-01T00:00:00Z"}, "data": "value"}
        dt = extract_timestamp(body, {}, field_paths=["meta.ts"])
        assert dt is not None
        assert dt.year == 2026

    def test_deeply_nested_field_auto_discovered(self):
        """Without field_paths, auto-discovery should find timestamps recursively."""
        body = {"response": {"metadata": {"updated_at": "2026-01-01T00:00:00Z"}}}
        dt = extract_timestamp(body, {})
        assert dt is not None

    def test_field_paths_tried_in_order(self):
        """First matching field_path wins."""
        body = {
            "stale_ts": "2020-01-01T00:00:00Z",
            "fresh_ts": "2026-01-01T00:00:00Z",
        }
        dt = extract_timestamp(body, {}, field_paths=["fresh_ts", "stale_ts"])
        assert dt is not None
        assert dt.year == 2026

    # -- Header fallback -----------------------------------------------------

    def test_header_fallback_when_body_has_no_timestamp(self):
        """Falls back to Last-Modified header when body yields nothing."""
        body = {"data": "no timestamps here"}
        headers = {"last-modified": "Wed, 15 Jan 2026 10:30:00 GMT"}
        dt = extract_timestamp(body, headers)
        assert dt is not None
        assert dt.year == 2026

    def test_header_fallback_date_header(self):
        """Date header is also a valid fallback."""
        body = {}
        headers = {"date": "Thu, 01 May 2026 12:00:00 GMT"}
        dt = extract_timestamp(body, headers)
        assert dt is not None

    def test_body_takes_priority_over_headers(self):
        """Body timestamp found → header not consulted."""
        body = {"updated_at": "2026-06-01T00:00:00Z"}
        headers = {"last-modified": "Wed, 01 Jan 2020 00:00:00 GMT"}
        dt = extract_timestamp(body, headers)
        assert dt is not None
        assert dt.year == 2026   # body wins

    # -- Missing / malformed -----------------------------------------------

    def test_missing_field_returns_none(self):
        body = {}
        assert extract_timestamp(body, {}) is None

    def test_malformed_date_string_returns_none(self):
        """Bad timestamp value → None, never raises."""
        body = {"timestamp": "not-a-date"}
        assert extract_timestamp(body, {}) is None

    def test_malformed_returns_none_not_exception(self):
        """Robustness: parsing errors are swallowed."""
        body = {"ts": "¯\\_(ツ)_/¯"}
        result = extract_timestamp(body, {})
        assert result is None

    def test_all_missing_returns_none(self):
        """No body fields, no headers → None."""
        assert extract_timestamp({}, {}) is None

    def test_explicit_field_path_not_found_falls_back_to_scan(self):
        """field_paths=['nonexistent'] misses, then auto-scan finds updated_at."""
        body = {"updated_at": "2026-01-01T00:00:00Z"}
        dt = extract_timestamp(body, {}, field_paths=["nonexistent_field"])
        assert dt is not None   # auto-scan fallback found updated_at

    # -- Return type ---------------------------------------------------------

    def test_returns_datetime_with_timezone(self):
        """Returned datetime must be timezone-aware (UTC)."""
        body = {"ts": "2026-01-01T00:00:00Z"}
        dt = extract_timestamp(body, {})
        assert dt is not None
        assert dt.tzinfo is not None

    def test_naive_datetime_in_body_returned_as_utc(self):
        """Naive ISO 8601 (no tz suffix) treated as UTC."""
        body = {"created_at": "2026-05-15T09:00:00"}
        dt = extract_timestamp(body, {})
        assert dt is not None
        assert dt.tzinfo is not None


# ===========================================================================
# compare_responses + extract_timestamp: used together (integration shape)
# ===========================================================================

class TestSharedUsedTogether:

    def test_two_responses_with_same_timestamp_compare_equal(self):
        """Determinism check + freshness check can both run on same body."""
        body = {"result": "ok", "ts": "2026-01-01T00:00:00Z"}
        assert compare_responses(body, body.copy()) is True
        dt = extract_timestamp(body, {})
        assert dt is not None

    def test_two_responses_differ_in_timestamp_only(self):
        """Bodies that differ only in timestamp value are not identical."""
        r1 = {"result": "ok", "ts": "2026-01-01T00:00:00Z"}
        r2 = {"result": "ok", "ts": "2026-01-02T00:00:00Z"}
        assert compare_responses(r1, r2) is False
