"""
fynor.monitoring.decision_logger — AI agent decision recorder.

Every AI agent decision monitored by Fynor is written to decision_log.jsonl.
This is the raw input to the ground truth database. Domain experts review
flagged decisions and label them CORRECT or INCORRECT — each label creates
one ground truth record.

Decision log schema:
  {
    "ts":              ISO-8601 UTC timestamp,
    "client_id":       anonymised client identifier,
    "domain":          domain ontology identifier,
    "agent_id":        identifier of the AI agent that made the decision,
    "agent_input":     JSON-serialised input to the agent,
    "agent_decision":  what the agent decided,
    "rules_checked":   list of ontology rule IDs evaluated,
    "violations":      list of rule IDs violated (empty = compliant),
    "flagged":         true when violations list is non-empty,
    "verdict":         null (pending review) | CORRECT | INCORRECT
  }

STATUS: Stub — full monitoring pipeline ships Phase C (Month 18+).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DECISION_LOG_PATH = Path.home() / ".fynor" / "decision_log.jsonl"


@dataclass
class DecisionLog:
    """One AI agent decision record."""

    client_id: str
    domain: str
    agent_id: str
    agent_input: str            # JSON string
    agent_decision: str
    rules_checked: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    flagged: bool = False
    verdict: str | None = None  # null | CORRECT | INCORRECT (set by domain expert)
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def log_decision(
    record: DecisionLog,
    path: Path | None = None,
) -> None:
    """
    Append one agent decision to the decision log.

    Args:
        record: DecisionLog dataclass.
        path:   Override the default log file location.
    """
    dest = path or Path(
        os.environ.get("FYNOR_DECISION_LOG_PATH", DEFAULT_DECISION_LOG_PATH)
    )
    dest.parent.mkdir(parents=True, exist_ok=True)

    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record)) + "\n")
