"""
fynor.intelligence — Self-learning and pattern recognition layer.

This module contains the three AI Agent Junctions and the statistical
pattern detection engine. The junctions require human review before
any output reaches the user or updates the pattern library.

Governing rule: AI proposes. Human approves. Automation executes.

Build sequence:
  Month 5   pattern_detector.py   — Statistical only, no AI. Build first.
  Month 7   failure_interpreter   — AI Junction 1 (after check data exists)
  Month 9   pattern_learner       — AI Junction 2 (after 50+ confirmed interpretations)
  Month 18  ontology_updater      — AI Junction 3 (Phase C, after client audits)

Pattern detection algorithms (no ML, pure statistics):
  1. Co-failure correlation  — which checks fail together?
  2. Latency drift           — is P95 moving directionally over 30 days?
  3. Time signature          — do failures cluster at specific hours?
"""

from fynor.intelligence.pattern_detector import PatternDetector, Pattern, Alert

__all__ = ["PatternDetector", "Pattern", "Alert"]
