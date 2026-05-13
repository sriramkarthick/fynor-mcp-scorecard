"""
fynor.intelligence.pattern_learner — AI Agent Junction 2.

Triggered when the confirmed failure interpretation queue accumulates
50+ entries with the same failure_type. Proposes a new pattern to add
to pattern_detector.py as a detection function.

STATUS: Stub — ships Month 9 (after 50+ confirmed interpretations exist).

Human review gate: proposed patterns are NEVER committed to pattern_detector.py
automatically. Sriram (and later a domain expert hire) reviews each proposal.
If approved → a new detection function is added to pattern_detector.py.
If rejected → the failure_type is flagged as "misclassified" and the
             model learns from the correction.

Why this matters:
  Each approved pattern makes every future check run cheaper and more accurate.
  Known patterns are detected statistically (no AI needed for classification),
  so the AI junction only fires for novel failures. Over time, the AI junction
  fires less and the automation spine handles more — the platform self-improves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ProposedPattern:
    """
    AI-proposed addition to the pattern detection library.

    Not committed to pattern_detector.py until human_approved is True.
    """

    pattern_type: str           # co_failure | latency_drift | time_signature | novel
    failure_type: str           # from FailureInterpretation.failure_type
    checks_involved: list[str]
    signature: dict             # detection signature: thresholds, time markers, etc.
    confidence: float
    supporting_evidence: list[str]   # failure interpretation IDs
    suggested_detection_code: str    # Python snippet for pattern_detector.py
    human_approved: bool = False
    approved_by: str = ""
    proposed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def propose_pattern(
    failure_type: str,
    confirmed_interpretations: list[dict],
    existing_patterns: list[dict],
) -> ProposedPattern | None:
    """
    Propose a new detection pattern from a cluster of confirmed failures.

    Returns None if fewer than 50 confirmed interpretations exist for this
    failure_type — minimum evidence threshold not yet met.

    Args:
        failure_type:               The common failure_type across interpretations.
        confirmed_interpretations:  Human-approved FailureInterpretations.
        existing_patterns:          Current confirmed pattern library entries.

    Returns:
        ProposedPattern (requires human review), or None.
    """
    if len(confirmed_interpretations) < 50:
        return None

    # TODO (Month 9): Replace with LLM call that:
    # 1. Analyses the 50+ interpretations for common structure
    # 2. Extracts a detection signature (thresholds, co-checks, time markers)
    # 3. Generates a Python detection function for pattern_detector.py
    # 4. Estimates confidence from evidence consistency

    return ProposedPattern(
        pattern_type="novel",
        failure_type=failure_type,
        checks_involved=[],
        signature={},
        confidence=0.0,
        supporting_evidence=[str(i.get("id", "")) for i in confirmed_interpretations[:10]],
        suggested_detection_code="# [Detection code will be generated here — ships Month 9]",
    )
