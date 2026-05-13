# ADR-01: Automation Spine + AI Agent Junction Architecture

**Status:** Accepted  
**Date:** 2026-05-13  
**Deciders:** Sriram Karthick (Fynor Technologies)

---

## Context

Fynor is a reliability measurement platform that itself uses AI agents as part of its
self-learning loop. This creates an architectural tension: a tool that measures AI
reliability must not have the same reliability failures it is designed to detect.

Three options were considered for how to structure decision-making across the platform:

1. **Full automation** — every action is deterministic code, no AI
2. **Full AI** — every check and pattern is AI-driven
3. **Hybrid with governance** — deterministic automation for repeatable work, AI with human gates for judgment

The key question: **which category of task belongs in automation, and which belongs in an AI agent junction?**

---

## Decision

**The Automation Spine + 3 AI Agent Junction architecture.**

**Governing rule:** AI proposes. Human approves. Automation executes.

**Classification test:** A task belongs in automation if and only if:
- The same input always produces the same correct output (deterministic)
- A human could write a complete specification for it in advance
- Failure is detectable by automated assertion

A task belongs in an AI agent junction if and only if:
- It requires reading and interpreting context to produce a correct output
- The space of valid outputs cannot be fully enumerated in advance
- A human expert could evaluate the output as correct or incorrect

---

## The Automation Spine

Every check run, scoring operation, history write, and pattern detection is automation.
These are fully deterministic: given the same server state, Fynor always produces the
same result. This is not a limitation — it is the core reliability guarantee.

```
fynor check
  → Adapter fires N requests
  → 8 deterministic checks evaluate responses
  → Scorer computes weighted grade (ADR-02)
  → Result written to history.jsonl
  → Pattern Detector runs 3 statistical algorithms
  → Patterns/Alerts written to patterns.jsonl / alerts.jsonl
```

No AI is involved anywhere in this path. No variance. No hallucination risk.

---

## The Three AI Agent Junctions

Three decision points in the platform require judgment that automation cannot provide
reliably. These are the only three places where AI is used.

### Junction 1 — Failure Interpretation Agent (Month 7)

**Trigger:** PatternDetector flags an anomaly.  
**Input:** Failure details + 30-day history + confirmed pattern library.  
**AI task:** Propose a root cause and specific remediation.  
**Output:** `FailureInterpretation` — held in review queue.  
**Human gate:** Approved or rejected by the operator.  
**On approval:** Enters the pattern library with `confirmed_by` field set.  
**On rejection:** Discarded. Failure type logged as `novel` for future training.

**Why this is a junction, not automation:** The root cause of a latency spike at 02:00 UTC
could be a cron job, a certificate rotation, a traffic wave, or a memory leak.
Determining which requires reading historical context and generating a targeted explanation.
Automation cannot do this reliably. AI can, with a human correction gate.

### Junction 2 — Pattern Learning Agent (Month 9)

**Trigger:** 50+ confirmed interpretations of the same failure type.  
**Input:** The confirmed interpretation corpus for that failure type.  
**AI task:** Propose a new detection function for `pattern_detector.py`.  
**Output:** `ProposedPattern` with code — held for review.  
**Human gate:** Approved by Fynor engineering before any code ships.  
**Threshold requirement:** 50 confirmed entries. This prevents noise from
becoming rules before statistical significance is established.

**Why this is a junction, not automation:** Writing a new statistical detection
function requires generalising from specific examples to an abstract rule. This
is a programming task requiring judgment — not a lookup.

### Junction 3 — Ontology Update Agent (Phase C, Month 18)

**Trigger:** Domain expert labels a new agent decision as CORRECT or INCORRECT.  
**Input:** Labeled decision + existing domain ontology + ground truth records.  
**AI task:** Propose a new rule for the domain ontology (`.ontology.json`).  
**Output:** `OntologyRule` — held for domain expert review.  
**Human gate:** Domain expert approves. Becomes a ground truth record.

**Why this is a junction, not automation:** Deriving a general rule from a specific
labeled example requires domain knowledge and reasoning about edge cases.
Only a domain expert can verify the proposed rule is correct for the domain.

---

## Consequences

**Positive:**
- Every check result is reproducible and auditable — no AI variance in core measurements
- The human approval gate at each junction creates an audit trail of every AI proposal
- The pattern library and ground truth database only contain human-verified entries
- Fynor's own reliability is demonstrable: the automation spine has deterministic behavior

**Negative:**
- Initial development is slower: automation must be fully specified before it ships
- Junction 1 (Month 7) means Fynor ships without AI-powered remediation advice initially
- Human approval gates create a throughput limit on how fast the pattern library can grow

**The throughput limit is a feature, not a bug.** A reliability platform that generates
recommendations faster than humans can verify them would have the same problem as
the systems it is designed to measure.

---

## References

- Christiano, P. et al. (2017). Deep Reinforcement Learning from Human Preferences. NeurIPS.
- Amodei, D. et al. (2016). Concrete Problems in AI Safety. arXiv:1606.06565.
- Google SRE Book (2016). Chapter 8: Release Engineering — on automation and human override.
