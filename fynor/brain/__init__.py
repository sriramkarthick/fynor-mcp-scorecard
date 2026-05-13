"""
fynor.brain — Company Brain standard (Phase D).

The domain ontology starts as Fynor's internal format for encoding
"what correct AI agent behaviour looks like in a specific domain."
Phase D packages it as an open standard — the Company Brain format.

Company Brain = domain ontology + version control + subscription feed.

Every company has institutional knowledge scattered across Slack, email,
and people's heads. When key people leave, the knowledge leaves with them.
AI agents cannot execute knowledge they cannot access.

The Company Brain solves this:
  1. Domain experts encode company know-how as ontology rules (OntologyRule format)
  2. Rules are version-controlled in a private Git repository
  3. AI agents query the Company Brain to verify decisions before executing
  4. Each flagged decision creates a new ground truth record
  5. Over time, the Company Brain becomes the authoritative record of
     "how this company's AI agents should behave" — executable by any agent

Company Brain file format (.ontology.json):
  {
    "domain":    "fintech_trading_compliance",
    "version":   "2.3.1",
    "org_id":    "anonymised",
    "rules":     [ ... OntologyRule objects ... ],
    "updated_at": "2028-03-15T00:00:00Z",
    "ground_truth_records": 47
  }

Build sequence:
  Month 18  — Internal ontology format (fynor.intelligence.ontology_updater)
  2027      — First client ontology (FinTech vertical, Phase C)
  2029      — Ontology v2 (second vertical)
  2030+     — Company Brain standard: open format, subscription feed (Phase D)
"""

from fynor.brain.schema import OntologyFile, OntologyRuleEntry

__all__ = ["OntologyFile", "OntologyRuleEntry"]
