"""
tests/certification/test_evaluator.py — Tests for the 30-day cert evaluator.

All cases from certification-loop-contract.md §Verifiable by are covered:
  - 30 consecutive passing days → CERTIFIED
  - 29 passing + 1 infra error → PENDING (only 29 qualifying)
  - 29 passing + 1 infra error + 1 more passing → CERTIFIED (31 lookback)
  - 1 failing day anywhere → SUSPENDED
  - No records for 5 days → SUSPENDED (unmonitored = fail)
  - All infra errors (60 days) → PENDING (never certified)
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fynor.certification.evaluator import (
    DayRecord,
    CERTIFICATION_WINDOW_DAYS,
    evaluate_certification_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _passing_day(d: date) -> DayRecord:
    return DayRecord(date=d, passed=True, fynor_infra_err=False, runs_count=1)

def _failing_day(d: date) -> DayRecord:
    return DayRecord(date=d, passed=False, fynor_infra_err=False, runs_count=1)

def _infra_err_day(d: date) -> DayRecord:
    return DayRecord(date=d, passed=False, fynor_infra_err=True, runs_count=0)

def _days_back(today: date, n: int) -> list[date]:
    """Return list of the last n dates ending at today."""
    return [today - timedelta(days=i) for i in range(n)]


TODAY = date(2026, 5, 15)


# ---------------------------------------------------------------------------
# CERTIFIED cases
# ---------------------------------------------------------------------------

class TestCertified:

    def test_30_consecutive_passing_days(self):
        """Classic case: 30 straight passing days → CERTIFIED."""
        records = [_passing_day(d) for d in _days_back(TODAY, 30)]
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        assert verdict == "CERTIFIED"
        assert qualifying == 30

    def test_more_than_30_passing_days(self):
        """45 passing days — certified after 30."""
        records = [_passing_day(d) for d in _days_back(TODAY, 45)]
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        assert verdict == "CERTIFIED"
        assert qualifying == 30

    def test_infra_error_expands_window_to_find_30(self):
        """29 passing + 1 infra error + 1 more passing → 31 lookback, 30 qualifying."""
        records = []
        dates = _days_back(TODAY, 31)
        for i, d in enumerate(dates):
            if i == 29:   # 30th day back is infra error
                records.append(_infra_err_day(d))
            else:
                records.append(_passing_day(d))
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        assert verdict == "CERTIFIED"
        assert qualifying == 30

    def test_multiple_infra_errors_still_certifies(self):
        """3 infra errors scattered — still finds 30 qualifying days in 33-day window."""
        records = []
        dates = _days_back(TODAY, 33)
        infra_err_indices = {5, 15, 25}
        for i, d in enumerate(dates):
            if i in infra_err_indices:
                records.append(_infra_err_day(d))
            else:
                records.append(_passing_day(d))
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        assert verdict == "CERTIFIED"
        assert qualifying == 30


# ---------------------------------------------------------------------------
# PENDING cases
# ---------------------------------------------------------------------------

class TestPending:

    def test_29_passing_plus_1_infra_error(self):
        """29 passing + 1 infra error = 29 qualifying, not 30 → PENDING."""
        records = []
        dates = _days_back(TODAY, 30)
        for i, d in enumerate(dates):
            if i == 29:   # oldest day is infra error
                records.append(_infra_err_day(d))
            else:
                records.append(_passing_day(d))
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        assert verdict == "PENDING"
        assert qualifying == 29

    def test_only_20_days_of_records(self):
        """Only 20 days of history — can't reach 30 qualifying → PENDING."""
        records = [_passing_day(d) for d in _days_back(TODAY, 20)]
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        # Day 21 back has no record → SUSPENDED (unmonitored = fail)
        assert verdict == "SUSPENDED"   # not PENDING — missing day = fail

    def test_all_infra_errors_60_days(self):
        """60 days of infra errors — can never reach 30 qualifying days → PENDING."""
        records = [_infra_err_day(d) for d in _days_back(TODAY, 60)]
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        assert verdict == "PENDING"
        assert qualifying == 0


# ---------------------------------------------------------------------------
# SUSPENDED cases
# ---------------------------------------------------------------------------

class TestSuspended:

    def test_single_failing_day_today(self):
        """A fail today → immediate suspension."""
        records = (
            [_failing_day(TODAY)]
            + [_passing_day(TODAY - timedelta(days=i)) for i in range(1, 30)]
        )
        verdict, _ = evaluate_certification_window(records, TODAY)
        assert verdict == "SUSPENDED"

    def test_single_failing_day_in_middle(self):
        """A fail on day 15 → suspended even with passing days before and after."""
        records = []
        for i in range(30):
            d = TODAY - timedelta(days=i)
            if i == 15:
                records.append(_failing_day(d))
            else:
                records.append(_passing_day(d))
        verdict, _ = evaluate_certification_window(records, TODAY)
        assert verdict == "SUSPENDED"

    def test_no_records_for_5_days(self):
        """5 missing days (no records) → unmonitored = fail → SUSPENDED."""
        # Records only go back 25 days; days 26-30 are missing
        records = [_passing_day(TODAY - timedelta(days=i)) for i in range(25)]
        verdict, _ = evaluate_certification_window(records, TODAY)
        assert verdict == "SUSPENDED"

    def test_all_failing_days(self):
        """30 consecutive failing days → SUSPENDED on day 1."""
        records = [_failing_day(d) for d in _days_back(TODAY, 30)]
        verdict, qualifying = evaluate_certification_window(records, TODAY)
        assert verdict == "SUSPENDED"
        assert qualifying == 0

    def test_fail_after_infra_error(self):
        """Infra error then fail — the fail still suspends."""
        records = (
            [_failing_day(TODAY)]
            + [_infra_err_day(TODAY - timedelta(days=1))]
            + [_passing_day(TODAY - timedelta(days=i)) for i in range(2, 30)]
        )
        verdict, _ = evaluate_certification_window(records, TODAY)
        assert verdict == "SUSPENDED"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_records_suspends(self):
        """No records at all → first day unmonitored → SUSPENDED."""
        verdict, qualifying = evaluate_certification_window([], TODAY)
        assert verdict == "SUSPENDED"
        assert qualifying == 0

    def test_exactly_30_qualifying_certifies(self):
        verdict, qualifying = evaluate_certification_window(
            [_passing_day(d) for d in _days_back(TODAY, 30)],
            TODAY,
        )
        assert verdict == "CERTIFIED"
        assert qualifying == CERTIFICATION_WINDOW_DAYS

    def test_return_type_is_tuple(self):
        records = [_passing_day(d) for d in _days_back(TODAY, 30)]
        result = evaluate_certification_window(records, TODAY)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_verdict_is_string_literal(self):
        records = [_passing_day(d) for d in _days_back(TODAY, 30)]
        verdict, _ = evaluate_certification_window(records, TODAY)
        assert verdict in ("CERTIFIED", "PENDING", "SUSPENDED")
