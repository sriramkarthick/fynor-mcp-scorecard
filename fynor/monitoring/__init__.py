"""
fynor.monitoring — Runtime monitoring layer (AI OS for Companies).

This module is the Phase C "AI OS" component. It continuously monitors
AI agent behaviour against domain ontology rules, records every decision,
and surfaces violations for human review.

The monitoring layer is what turns Fynor from a testing tool into
operating infrastructure:

  BEFORE (open-loop):
    AI agent makes decision → decision executed → no record → no learning

  AFTER (closed-loop):
    AI agent makes decision
      → monitoring layer checks against domain ontology rules
      → decision recorded in decision_log.jsonl
      → violation flagged → domain expert reviews → ground truth record created
      → dashboard: "99.2% compliance with FINRA rule 4370 last quarter"
      → audit trail queryable by regulators

This is the AI OS layer. Every company AI decision becomes legible,
queryable, and auditable for the first time.

Build sequence:
  Month 18  — Decision logger (this module, stub)
  Month 20  — Ontology rule evaluator (v1.0)
  2027+     — Full runtime monitoring with streaming ingestion (Phase C)
"""

from fynor.monitoring.decision_logger import DecisionLog, log_decision

__all__ = ["DecisionLog", "log_decision"]
