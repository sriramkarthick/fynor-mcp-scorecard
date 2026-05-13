"""
fynor.history — Append-only check result log.

Every check run writes exactly one JSONL row. This file is never modified,
only appended. It is the seed of the self-learning loop: pattern_detector.py
reads it, confirms patterns, and the ground truth database grows from it.

Schema (one row per check per run):
  {
    "ts":      ISO-8601 UTC timestamp,
    "target":  URL or identifier of checked interface,
    "type":    interface type — mcp | rest | graphql | grpc | websocket | soap | cli,
    "check":   check name — latency_p95 | error_rate | schema | retry |
                            auth_token | rate_limit | timeout | log_completeness,
    "score":   0–100 numeric score,
    "passed":  true | false,
    "value":   raw measured value (ms, %, bool — type depends on check),
    "detail":  human-readable explanation of the result
  }
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


# Default location: ~/.fynor/history.jsonl
# Override with FYNOR_HISTORY_PATH env var.
DEFAULT_HISTORY_PATH = Path.home() / ".fynor" / "history.jsonl"


@dataclass
class CheckResult:
    """Structured result from a single check run."""

    check: str          # e.g. "latency_p95"
    passed: bool
    score: int          # 0–100
    value: float | str | None = None   # raw measured value
    detail: str = ""    # plain-English explanation


def append_result(
    target: str,
    interface_type: str,
    result: CheckResult,
    path: Path | None = None,
) -> None:
    """
    Append one check result row to the history log.

    Creates the file and parent directories if they do not exist.
    This function is the only write path — all reads go through
    fynor.intelligence.pattern_detector.

    Args:
        target:         URL or identifier of the checked interface.
        interface_type: One of: mcp | rest | graphql | grpc | websocket | soap | cli.
        result:         CheckResult dataclass from any check module.
        path:           Override the default history file location.
    """
    dest = path or Path(os.environ.get("FYNOR_HISTORY_PATH", DEFAULT_HISTORY_PATH))
    dest.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "type": interface_type,
        **asdict(result),
    }

    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def read_history(
    target: str | None = None,
    interface_type: str | None = None,
    check: str | None = None,
    path: Path | None = None,
) -> list[dict]:
    """
    Read history rows, optionally filtered.

    Args:
        target:         Filter to a specific target URL. None = all targets.
        interface_type: Filter to a specific interface type. None = all types.
        check:          Filter to a specific check name. None = all checks.
        path:           Override the default history file location.

    Returns:
        List of matching history rows as dicts, oldest first.
    """
    dest = path or Path(os.environ.get("FYNOR_HISTORY_PATH", DEFAULT_HISTORY_PATH))
    if not dest.exists():
        return []

    rows = []
    with dest.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            if target and row.get("target") != target:
                continue
            if interface_type and row.get("type") != interface_type:
                continue
            if check and row.get("check") != check:
                continue

            rows.append(row)

    return rows
