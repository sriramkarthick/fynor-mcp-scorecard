"""
fynor.intelligence.failure_interpreter — AI Agent Junction 1.

Triggered when pattern_detector flags an anomaly. Reads the failure,
the 30-day history for the target, and the confirmed pattern library.
Proposes a specific remediation recommendation.

STATUS: Stub — AI integration ships Month 7 (after check data exists).

Human review gate: recommendations are NEVER sent to the developer automatically.
Every recommendation goes to a review queue. Only approved recommendations
enter the pattern library with a confirmed_by field.

Why this is an AI junction and not automation:
  Interpreting WHY a check failed requires reading context — historical trends,
  known patterns, server behaviour — and generating a specific, actionable
  explanation. Automation cannot do this reliably. AI can, with a human
  correction gate to catch misclassifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class FailureInterpretation:
    """
    AI-proposed interpretation of a check failure.

    Not sent to the developer until human_approved is True.
    """

    target: str
    check: str
    failure_type: str           # e.g. "credential_rotation_90d"
    confidence: float           # 0.0–1.0
    matched_pattern: str        # pattern ID if matched, else "novel"
    root_cause: str             # plain English explanation
    recommendation: str         # specific remediation
    remediation_code: str       # code sample when applicable (empty string if none)
    requires_human_review: bool = True
    human_approved: bool = False
    approved_by: str = ""
    proposed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def interpret_failure(
    target: str,
    check: str,
    history_rows: list[dict],
    pattern_library: list[dict],
) -> FailureInterpretation:
    """
    Propose an interpretation for a check failure.

    Month 7 implementation will call an LLM with a structured prompt
    containing the failure, history, and matched patterns. This stub
    returns a placeholder interpretation for testing the review queue.

    Args:
        target:          URL of the checked interface.
        check:           Check name that failed.
        history_rows:    Last 30 days of history rows for this target.
        pattern_library: Confirmed patterns from pattern_library.jsonl.

    Returns:
        FailureInterpretation — requires human approval before use.
    """
    # TODO (Month 7): Replace with LLM call structured as:
    # prompt = _build_interpretation_prompt(target, check, history_rows, pattern_library)
    # response = llm.call(prompt)
    # return _parse_interpretation(response)

    matched = _match_pattern(check, history_rows, pattern_library)

    return FailureInterpretation(
        target=target,
        check=check,
        failure_type="unclassified",
        confidence=0.0,
        matched_pattern=matched or "novel",
        root_cause="[AI interpretation not yet implemented — ships Month 7]",
        recommendation="[Specific remediation will be generated here]",
        remediation_code="",
        requires_human_review=True,
    )


def _match_pattern(
    check: str,
    history_rows: list[dict],
    pattern_library: list[dict],
) -> str | None:
    """
    Attempt to match the failure against the confirmed pattern library.

    Returns the pattern_id of the best match, or None if no match found.
    Statistical matching only — no AI required for this step.
    """
    for pattern in pattern_library:
        if check in pattern.get("checks_involved", []):
            return pattern.get("pattern_id", "unknown")
    return None
