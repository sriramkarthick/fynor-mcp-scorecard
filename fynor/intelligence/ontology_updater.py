"""
fynor.intelligence.ontology_updater — AI Agent Junction 3.

Phase C component. Triggered when a Phase C client audit flags a domain
decision error that has no matching ontology rule. Proposes a new rule
for the domain ontology; a domain expert (compliance officer, risk manager)
reviews and labels it. Approved rules become ground truth records.

STATUS: Stub — ships Month 18 (Phase C entry, after first client audit).

Human review gate: NO ontology rule is committed without expert review.
This is the mechanism that grows the ground truth database. Every approved
rule represents labeled domain-expert data that cannot be replicated by
prompting an LLM — it requires real production data from real audits.

Why this is the most defensible component:
  The ground truth database (accumulated from these expert-approved rules)
  is what an acquirer is actually buying at exit. The software is replaceable.
  The labeled data is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class OntologyRule:
    """
    A proposed addition to the domain ontology.

    Not committed to the ontology repository until expert_approved is True.
    """

    domain: str                 # e.g. "fintech_trading_compliance"
    rule_id: str                # e.g. "rule-XXXX" (assigned on approval)
    description: str
    condition: str              # machine-readable condition expression
    expected_action: str        # what the AI agent should do
    failure_mode: str           # what happens when the agent fails this rule
    severity: str               # CRITICAL | HIGH | MEDIUM | LOW
    source: str                 # regulatory reference or internal standard
    confidence: float
    supporting_decisions: list[str]   # ground truth record IDs that support this rule
    expert_approved: bool = False
    approved_by: str = ""
    approved_date: str = ""
    ground_truth_records: int = 0
    proposed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class GroundTruthRecord:
    """
    One labeled AI agent decision — the atomic unit of the moat.

    Created when a domain expert reviews a flagged decision and labels it
    CORRECT or INCORRECT. These records accumulate into the ground truth
    database that makes Phase C defensible at exit.

    Growth math:
      Year 3 (2029): 10 clients × 50 decisions/month = 500 records/month
      Year 4 (2030): 25 clients                      = 1,250 records/month
      Moat becomes defensible at ~10,000+ records (estimated late 2030).
    """

    record_id: str
    domain: str
    jurisdiction: str
    rule: str
    agent_input: str            # JSON-serialised agent input
    agent_decision: str         # what the agent decided
    verdict: str                # CORRECT | INCORRECT
    correct_decision: str       # what the agent should have decided
    auditor: str                # anonymised domain expert ID
    audit_date: str
    client_id: str              # anonymised client ID


def propose_rule(
    domain: str,
    flagged_decision: dict,
    existing_rules: list[dict],
    similar_decisions: list[dict],
) -> OntologyRule | None:
    """
    Propose a new domain ontology rule from a flagged agent decision.

    Returns None if the flagged decision matches an existing rule —
    no new rule is needed, the existing rule was violated.

    Args:
        domain:             Domain identifier (e.g. "fintech_trading_compliance").
        flagged_decision:   The AI agent decision that violated domain expectations.
        existing_rules:     Current ontology rules for this domain.
        similar_decisions:  Past decisions with similar characteristics.

    Returns:
        OntologyRule (requires expert review), or None.
    """
    # Check if an existing rule already covers this decision
    for rule in existing_rules:
        if _decision_matches_rule(flagged_decision, rule):
            return None  # existing rule was violated, no new rule needed

    # TODO (Month 18): Replace with LLM call that:
    # 1. Reads the flagged decision, domain context, and similar decisions
    # 2. Identifies the violated business/compliance constraint
    # 3. Expresses it as a machine-readable condition + expected action
    # 4. Estimates severity based on domain context

    return OntologyRule(
        domain=domain,
        rule_id="rule-PENDING",
        description="[Rule description will be generated here — ships Month 18]",
        condition="[Machine-readable condition]",
        expected_action="[Expected agent action]",
        failure_mode="[Failure mode description]",
        severity="HIGH",
        source="[Regulatory reference or internal standard]",
        confidence=0.0,
        supporting_decisions=[],
    )


def _decision_matches_rule(decision: dict, rule: dict) -> bool:
    """
    Check whether a flagged decision is covered by an existing rule.
    Statistical matching only — no AI.
    """
    # TODO: implement condition matching logic in Month 18
    return False
