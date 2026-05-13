"""
fynor.brain.schema — Company Brain data model.

The canonical data structures for the domain ontology / Company Brain standard.
These are the types that flow between the intelligence layer (which creates rules)
and the monitoring layer (which enforces them at runtime).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class OntologyRuleEntry:
    """
    One rule in the Company Brain.

    Rules encode what "correct AI agent behaviour" looks like in one domain.
    They are built from real production audits, reviewed by domain experts,
    and version-controlled as the company's executable institutional knowledge.

    Example (FinTech trading compliance):
      rule_id:          "rule-0042"
      description:      "Trading AI must flag transactions above reporting threshold"
      condition:        "transaction.amount > reporting_threshold_usd"
      expected_action:  "GENERATE_FLAG"
      failure_mode:     "SILENT_APPROVAL"
      severity:         "CRITICAL"
      source:           "FINRA Rule 4370"
    """

    rule_id: str
    description: str
    condition: str              # machine-readable condition expression
    expected_action: str        # what the AI agent should do when condition is true
    failure_mode: str           # label for what happens when the agent fails this rule
    severity: str               # CRITICAL | HIGH | MEDIUM | LOW
    source: str                 # regulatory reference, internal policy, or observed pattern
    confirmed_by: str           # domain expert ID (anonymised)
    confirmed_date: str
    ground_truth_records: int = 0   # count of ground truth records backing this rule
    version: str = "1.0.0"


@dataclass
class OntologyFile:
    """
    The Company Brain file — a versioned collection of domain rules.

    Serialises to / deserialises from .ontology.json.
    Version-controlled in a private Git repository (one file per domain).

    At Phase C launch: one file, 20–50 rules, FinTech vertical.
    At Phase D: multiple files across 3+ verticals, open subscription format.
    """

    domain: str                     # e.g. "fintech_trading_compliance"
    version: str                    # semver: "2.3.1"
    jurisdiction: str               # e.g. "US" | "EU" | "global"
    org_id: str                     # anonymised organisation identifier
    rules: list[OntologyRuleEntry]
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ground_truth_records: int = 0   # total GT records backing this ontology version
    schema_version: str = "1"       # Company Brain format version (not ontology version)

    def get_rule(self, rule_id: str) -> OntologyRuleEntry | None:
        """Return a rule by ID, or None if not found."""
        return next((r for r in self.rules if r.rule_id == rule_id), None)

    def critical_rules(self) -> list[OntologyRuleEntry]:
        """Return all CRITICAL severity rules."""
        return [r for r in self.rules if r.severity == "CRITICAL"]

    def summary(self) -> str:
        """One-line summary for logging and dashboards."""
        return (
            f"OntologyFile(domain={self.domain!r}, version={self.version}, "
            f"rules={len(self.rules)}, gt_records={self.ground_truth_records})"
        )
