"""
fynor.certification.evaluator — 30-day certification window evaluator.

Reference implementation from certification-loop-contract.md.

The evaluator runs daily via EventBridge cron (infrastructure/lambdas/cert_evaluator.py).
It reads the last 30 days of DailyRecords and returns a verdict plus a count
of qualifying (non-infra-error) passing days.

Key rule: a day when Fynor's own infrastructure failed (fynor_infra_err=True)
is EXCLUDED from evaluation — neither pass nor fail. The window expands
(up to 60 days lookback) until 30 qualifying days are found or a failure occurs.
This prevents Fynor's own outages from causing spurious suspension.

See docs/sla.md for the FYNOR_INFRA_ERROR SLA clause.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

CERTIFICATION_WINDOW_DAYS = 30   # locked — do not make configurable
MIN_RUNS_PER_DAY = 1             # at least one check run must exist per day
MAX_LOOKBACK_DAYS = 60           # hard ceiling on window expansion

CertVerdict = Literal["CERTIFIED", "PENDING", "SUSPENDED"]


@dataclass
class DayRecord:
    """One day's check result for a single target.

    Stored in the ``fynor-daily-results`` DynamoDB table (one row per
    target_hash + date). Written after every check run by the orchestrator.
    Best-of-day: if multiple runs happen on the same day, only the best
    grade is retained.
    """

    date: date
    passed: bool
    fynor_infra_err: bool   # True = Fynor's infra caused the failure, not the target
    runs_count: int


def evaluate_certification_window(
    records: list[DayRecord],
    today: date,
) -> tuple[CertVerdict, int]:
    """
    Evaluate whether a target deserves CERTIFIED, PENDING, or SUSPENDED status.

    Args:
        records: All DayRecord objects available for this target (any date range).
                 Records outside the evaluation window are ignored.
        today:   The date to evaluate from (normally datetime.date.today() UTC).

    Returns:
        (verdict, qualifying_days_count) where:
          - verdict is "CERTIFIED", "PENDING", or "SUSPENDED"
          - qualifying_days_count is the number of non-infra-error passing days found

    Rules (from certification-loop-contract.md):
        1. Walk backwards from today, up to MAX_LOOKBACK_DAYS.
        2. For each day:
           - No record: counts as FAIL (server unmonitored → SUSPENDED).
             Only within the first 30 lookback days — beyond that the window
             may still expand to collect 30 qualifying days.
           - fynor_infra_err=True: day EXCLUDED (neither pass nor fail).
             Shrinks effective window; look further back.
           - passed=True: qualifying day (+1).
           - passed=False: SUSPENDED immediately.
        3. Stop when 30 qualifying days found → CERTIFIED.
        4. Stop when a fail/unmonitored day found → SUSPENDED.
        5. If max lookback reached without 30 qualifying days → PENDING.
    """
    record_map: dict[date, DayRecord] = {r.date: r for r in records}

    qualifying_days = 0
    lookback_days = 0
    current_date = today

    while qualifying_days < CERTIFICATION_WINDOW_DAYS and lookback_days < MAX_LOOKBACK_DAYS:
        record = record_map.get(current_date)

        if record is None:
            # Day not monitored.
            # Within the first 30-day nominal window (lookback_days < 30):
            #   no record = unmonitored = SUSPENDED immediately.
            # Beyond 30 days (window expanded to compensate for infra errors):
            #   no record = we've run out of history → PENDING (insufficient data,
            #   but no confirmed failures either).
            if lookback_days < CERTIFICATION_WINDOW_DAYS:
                return "SUSPENDED", qualifying_days
            else:
                return "PENDING", qualifying_days

        if record.fynor_infra_err:
            # Excluded day — don't count toward qualifying days, don't fail.
            # The window will expand to find the 30 qualifying days.
            pass
        elif not record.passed:
            # Actual target failure → suspend immediately.
            return "SUSPENDED", qualifying_days
        else:
            qualifying_days += 1

        current_date -= timedelta(days=1)
        lookback_days += 1

    if qualifying_days >= CERTIFICATION_WINDOW_DAYS:
        return "CERTIFIED", qualifying_days

    return "PENDING", qualifying_days
