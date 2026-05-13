"""
fynor.intelligence.pattern_detector — Statistical pattern detection engine.

Reads history.jsonl and detects three types of reliability patterns.
No ML. No AI. Pure statistics. Same input always produces same output.
This is part of the Automation Spine, not an AI Agent Junction.

Three detection algorithms:
  1. Co-failure correlation  — checks that fail together have a shared root cause
  2. Latency drift           — P95 trending upward indicates capacity or regression issues
  3. Time signature          — failures clustered at specific hours indicate cron jobs,
                               token rotation cycles, or scheduled maintenance gaps

Output:
  Patterns  — confirmed recurring failure signatures
  Alerts    — triggered threshold breaches requiring attention

Patterns are written to ~/.fynor/patterns.jsonl for human review.
Only human-approved patterns enter the Pattern Library (pattern_library.jsonl).
"""

from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from fynor.history import read_history

DEFAULT_PATTERN_PATH = Path.home() / ".fynor" / "patterns.jsonl"
DEFAULT_ALERT_PATH = Path.home() / ".fynor" / "alerts.jsonl"


@dataclass
class Pattern:
    """A recurring failure signature detected across multiple check runs."""

    pattern_type: str           # co_failure | latency_drift | time_signature
    target: str
    checks_involved: list[str]
    confidence: float           # 0.0–1.0
    description: str
    evidence: dict              # supporting statistics
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "pending"     # pending | confirmed | rejected


@dataclass
class Alert:
    """A threshold breach that does not yet have a confirmed pattern."""

    alert_type: str             # latency_regression | high_error_rate | auth_failure_spike
    target: str
    check: str
    current_value: float
    baseline_value: float
    z_score: float
    description: str
    triggered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PatternDetector:
    """
    Statistical pattern detection over the check history log.

    Usage:
        detector = PatternDetector()
        patterns, alerts = detector.run(target="https://api.example.com")
    """

    # Thresholds — locked in ADR-04. Do not adjust without a superseding ADR.
    COFAILURE_THRESHOLD = 0.70      # checks failing together in ≥70% of runs
    DRIFT_ZSCORE_THRESHOLD = 2.5    # z-score above this triggers a drift alert
    TIME_HOT_HOUR_MULTIPLIER = 3.0  # 3× expected rate = time signature
    MIN_RUNS_FOR_PATTERN = 10       # minimum runs for co-failure and drift algorithms
    # Time-signature needs more data: 20 runs AND 48h span to prevent
    # bootstrapping false positives. A new client running 10 checks in a
    # 2-hour window has all data in 2 buckets — the 24-bucket histogram is
    # degenerate. Without a minimum time span, the 3× multiplier fires trivially.
    TIME_SIG_MIN_RUNS = 20
    TIME_SIG_MIN_SPAN_HOURS = 48.0

    def __init__(
        self,
        history_path: Path | None = None,
        pattern_path: Path | None = None,
        alert_path: Path | None = None,
    ) -> None:
        self._history_path = history_path
        self._pattern_path = pattern_path or Path(
            os.environ.get("FYNOR_PATTERN_PATH", DEFAULT_PATTERN_PATH)
        )
        self._alert_path = alert_path or Path(
            os.environ.get("FYNOR_ALERT_PATH", DEFAULT_ALERT_PATH)
        )

    def run(
        self,
        target: str | None = None,
        window_days: int = 30,
    ) -> tuple[list[Pattern], list[Alert]]:
        """
        Run all three detection algorithms against the history log.

        Args:
            target:       Limit detection to a specific target. None = all targets.
            window_days:  How many days of history to consider (default 30).

        Returns:
            Tuple of (patterns, alerts). Patterns are also written to patterns.jsonl.
        """
        rows = read_history(target=target, path=self._history_path)
        if len(rows) < self.MIN_RUNS_FOR_PATTERN:
            return [], []

        patterns: list[Pattern] = []
        alerts: list[Alert] = []

        # Group rows by target for per-target analysis
        by_target: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_target[row["target"]].append(row)

        for tgt, tgt_rows in by_target.items():
            if target and tgt != target:
                continue
            if len(tgt_rows) < self.MIN_RUNS_FOR_PATTERN:
                continue

            patterns.extend(self._detect_cofailures(tgt, tgt_rows))
            alerts.extend(self._detect_drift(tgt, tgt_rows))
            patterns.extend(self._detect_time_signature(tgt, tgt_rows))

        self._write_patterns(patterns)
        self._write_alerts(alerts)
        return patterns, alerts

    # ------------------------------------------------------------------ #
    # Algorithm 1 — Co-failure correlation                                #
    # ------------------------------------------------------------------ #

    def _detect_cofailures(
        self, target: str, rows: list[dict]
    ) -> list[Pattern]:
        """
        Find checks that fail together in ≥70% of runs.

        Method: group rows by run timestamp (same-second bucket),
        then compute co-occurrence rate for every pair of checks.
        """
        # Group rows into runs (bucket by minute for tolerance)
        runs: dict[str, dict[str, bool]] = defaultdict(dict)
        for row in rows:
            minute = row["ts"][:16]  # truncate to minute
            runs[minute][row["check"]] = not row.get("passed", True)

        if len(runs) < self.MIN_RUNS_FOR_PATTERN:
            return []

        run_list = list(runs.values())
        checks = list({c for run in run_list for c in run})

        patterns: list[Pattern] = []
        seen_pairs: set[frozenset] = set()

        for i, c1 in enumerate(checks):
            for c2 in checks[i + 1:]:
                pair = frozenset({c1, c2})
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                both_fail = sum(
                    1 for run in run_list
                    if run.get(c1, False) and run.get(c2, False)
                )
                either_fail = sum(
                    1 for run in run_list
                    if run.get(c1, False) or run.get(c2, False)
                )
                if either_fail == 0:
                    continue

                rate = both_fail / either_fail
                if rate >= self.COFAILURE_THRESHOLD and both_fail >= 3:
                    patterns.append(Pattern(
                        pattern_type="co_failure",
                        target=target,
                        checks_involved=[c1, c2],
                        confidence=round(rate, 3),
                        description=(
                            f"{c1} and {c2} fail together in "
                            f"{rate:.0%} of runs ({both_fail} occurrences). "
                            "Likely a shared root cause."
                        ),
                        evidence={"co_occurrence_rate": rate, "count": both_fail},
                    ))

        return patterns

    # ------------------------------------------------------------------ #
    # Algorithm 2 — Latency drift                                         #
    # ------------------------------------------------------------------ #

    def _detect_drift(self, target: str, rows: list[dict]) -> list[Alert]:
        """
        Detect directional movement in P95 latency over time.

        Method: compute rolling 30-day average and compare to overall baseline.
        Trigger alert when z-score exceeds threshold.
        """
        latency_rows = [
            r for r in rows
            if r.get("check") == "latency_p95" and r.get("value") is not None
        ]
        if len(latency_rows) < self.MIN_RUNS_FOR_PATTERN:
            return []

        values = [float(r["value"]) for r in latency_rows]
        if len(values) < 4:
            return []

        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        if stdev == 0:
            return []

        recent = values[-min(5, len(values)):]
        recent_mean = statistics.mean(recent)
        z = (recent_mean - mean) / stdev

        if abs(z) < self.DRIFT_ZSCORE_THRESHOLD:
            return []

        direction = "increased" if z > 0 else "decreased"
        return [Alert(
            alert_type="latency_regression" if z > 0 else "latency_improvement",
            target=target,
            check="latency_p95",
            current_value=round(recent_mean, 2),
            baseline_value=round(mean, 2),
            z_score=round(z, 2),
            description=(
                f"P95 latency has {direction} from baseline {mean:.0f}ms "
                f"to recent {recent_mean:.0f}ms (z-score: {z:.1f}). "
                "Investigate for capacity issues or regressions."
            ),
        )]

    # ------------------------------------------------------------------ #
    # Algorithm 3 — Time signature                                        #
    # ------------------------------------------------------------------ #

    def _detect_time_signature(
        self, target: str, rows: list[dict]
    ) -> list[Pattern]:
        """
        Detect failures clustering at specific hours of the day.

        Method: build a 24-bucket hour histogram of failures.
        Flag any hour where the failure rate is 3× the expected rate.

        Common causes: auth token rotation at midnight, cron jobs, backups.

        Guards:
        - Requires TIME_SIG_MIN_RUNS total runs (not just failures) to prevent
          false positives from small samples.
        - Requires TIME_SIG_MIN_SPAN_HOURS of history span. A new client running
          10 checks in a 2-hour window has all data in 2 of 24 buckets —
          the histogram is degenerate and the 3× threshold fires trivially.
        """
        if len(rows) < self.TIME_SIG_MIN_RUNS:
            return []

        # Verify history spans at least TIME_SIG_MIN_SPAN_HOURS
        try:
            timestamps = sorted(
                datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
                for r in rows
                if r.get("ts")
            )
            if timestamps:
                span_hours = (
                    (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
                )
                if span_hours < self.TIME_SIG_MIN_SPAN_HOURS:
                    return []
        except Exception:  # noqa: BLE001
            return []

        failure_rows = [r for r in rows if not r.get("passed", True)]
        if len(failure_rows) < 5:
            return []

        # Count failures per hour
        hour_counts: dict[int, int] = defaultdict(int)
        for row in failure_rows:
            try:
                hour = datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).hour
                hour_counts[hour] += 1
            except Exception:  # noqa: BLE001
                continue

        total_failures = sum(hour_counts.values())
        expected_per_hour = total_failures / 24.0
        if expected_per_hour < 1:
            return []

        patterns: list[Pattern] = []
        for hour, count in hour_counts.items():
            rate = count / expected_per_hour
            if rate >= self.TIME_HOT_HOUR_MULTIPLIER:
                patterns.append(Pattern(
                    pattern_type="time_signature",
                    target=target,
                    checks_involved=list({r["check"] for r in failure_rows}),
                    confidence=round(min(rate / 10.0, 1.0), 3),
                    description=(
                        f"Failures cluster at hour {hour:02d}:00 UTC "
                        f"({count} failures = {rate:.1f}x expected rate). "
                        "Common causes: auth token rotation, cron jobs, scheduled maintenance."
                    ),
                    evidence={
                        "hot_hour": hour,
                        "failure_count": count,
                        "expected_rate": round(expected_per_hour, 2),
                        "multiplier": round(rate, 2),
                    },
                ))

        return patterns

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _write_patterns(self, patterns: list[Pattern]) -> None:
        if not patterns:
            return
        self._pattern_path.parent.mkdir(parents=True, exist_ok=True)
        with self._pattern_path.open("a", encoding="utf-8") as fh:
            for p in patterns:
                fh.write(json.dumps(asdict(p)) + "\n")

    def _write_alerts(self, alerts: list[Alert]) -> None:
        if not alerts:
            return
        self._alert_path.parent.mkdir(parents=True, exist_ok=True)
        with self._alert_path.open("a", encoding="utf-8") as fh:
            for a in alerts:
                fh.write(json.dumps(asdict(a)) + "\n")
