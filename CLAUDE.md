# CLAUDE.md — Fynor Agent Instructions

**Last updated:** 2026-05-13

This file is the agent harness for the Fynor reliability platform repository.
Read it first. It tells you which documents govern which decisions, how to route
yourself by task type, and what quality gates must pass before any commit.

---

## Governing Documents (read before touching any code)

These four ADRs are LOCKED constraints, not suggestions. Every implementation
decision must be consistent with them. If you believe an ADR is wrong, propose
an amendment — do not silently deviate.

| Document | What it locks | Status |
|----------|--------------|--------|
| `docs/adr/ADR-01-architecture-principles.md` | Which decisions are automation vs AI junction | LOCKED |
| `docs/adr/ADR-02-scoring-weights.md` | Scoring weights (30/40/30) and security cap rule | LOCKED |
| `docs/adr/ADR-03-check-taxonomy.md` | Exactly 8 checks, no more without taxonomy entry | LOCKED |
| `docs/adr/ADR-04-threshold-justification.md` | z=2.5, 70%, 3× thresholds with citations | LOCKED |

---

## Context by Task Type

### Writing or modifying a check (`fynor/checks/`)
1. Read `docs/adr/ADR-03-check-taxonomy.md` — is this check in the taxonomy?
2. Read `docs/tasks/check-implementation-contract.md` — the function contract
3. Every check must return `CheckResult(score: int, passed: bool, detail: str)`
4. Every check must be deterministic — no randomness, no timestamp-dependent logic
5. Run: `pytest tests/checks/ -v` — must pass before committing

### Modifying the scorer (`fynor/scorer.py`)
1. Read `docs/adr/ADR-02-scoring-weights.md` — weights are LOCKED
2. Read `docs/tasks/api-implementation-contract.md` — the `ScorecardResult` contract
3. Security cap rule: auth_token == 0 → final grade ≤ D (max weighted_score = 59.0)
4. Run: `pytest tests/test_scorer.py -v` — all 10 cases must pass

### Writing the hosted API (`fynor/api/`)
1. Read `docs/tasks/api-implementation-contract.md` — FastAPI + Lambda + DynamoDB specs
2. Read `docs/api-specification.md` — REST API schema (source of truth for request/response)
3. Read `docs/tasks/build-sequence.md` — which month this feature belongs to
4. Framework: FastAPI only. No Flask, no Django.
5. All endpoints must have Pydantic request/response models matching `docs/api-specification.md`

### Implementing the certification loop
1. Read `docs/tasks/certification-loop-contract.md` — EventBridge cron + DynamoDB TTL spec
2. Read `docs/sla.md` — the FYNOR_INFRA_ERROR clause must be implementable
3. The 30-day window uses per-day pass/fail records, not a counter

### Working on intelligence features (`fynor/intelligence/`)
1. Read `docs/adr/ADR-01-architecture-principles.md` — classification test (automation vs AI junction)
2. Read `docs/adr/ADR-04-threshold-justification.md` — thresholds are LOCKED constants
3. Pattern detector: thresholds must be class constants, not configurable at runtime
4. Junction 1 (failure interpreter): ships Month 7 — do not build before Month 6 MVP is done

### Infrastructure / deployment work
1. Read `docs/deployment-architecture.md` — AWS topology
2. Read `docs/tasks/api-implementation-contract.md` — Lambda fan-out pattern
3. Read `docs/tasks/certification-loop-contract.md` — EventBridge cron spec
4. Read `docs/privacy-data-handling.md` — encryption at rest requirements

### Research / academic writing
1. Read `docs/research/paper.md` — citations, formal definitions, evaluation study designs
2. Read `docs/research/meta-evaluation.md` — how Fynor measures its own accuracy
3. Every statistical number must trace to a citation in `paper.md` Section 10 (References)

### Business / pricing / market
1. Read `docs/business/financial-model.md` — tier pricing, ARR projections, exit math
2. Read `docs/business/market-sizing.md` — TAM/SAM/SOM anchors
3. Read `docs/business/competitive-moat.md` — ground truth DB moat and patent strategy

---

## Quality Gates — Every PR Must Pass

```bash
# Lint
ruff check .

# Type checking (strict mode)
mypy fynor/ --strict

# Tests with coverage
pytest --cov=fynor --cov-report=term-missing --cov-fail-under=90

# All three must exit 0 before any merge
```

These gates are non-negotiable. If mypy strict fails on a file you did not touch,
investigate — do not suppress with `# type: ignore` without a comment explaining why.

---

## Build Sequence (what exists when)

See `docs/tasks/build-sequence.md` for the full month-by-month plan. Summary:

| Month | What ships |
|-------|-----------|
| 1–2 | CLI pip-installable, 8 checks, scoring, pytest green |
| 3 | fynor.tech landing page + waitlist |
| 4–5 | FastAPI hosted service, Lambda workers, DynamoDB, Pro tier |
| 6 | Badge CDN (CloudFront), certification endpoint, 30-day cron |
| 7 | Junction 1 — Claude API failure interpreter (async) |
| 8 | REST adapter v0.2 |
| 9 | Junction 2 — pattern detector writes back, human approval gate |

Do not build Month 7+ features before Month 1–6 is done and tested.

---

## Feedback Loop — Spec vs Implementation Gaps

When a bug is found, classify it before fixing:

**Type A — Spec-to-code gap:** The spec (ADR / task contract) is correct, the code
is wrong. Fix the code. File a note under the relevant check's `Known Failure Modes`
in `docs/adr/ADR-03-check-taxonomy.md` if the bug reveals a false positive/negative.

**Type B — Intent-to-spec gap:** The code does what the spec says, but the spec
was wrong about what the check should do. Propose an ADR amendment. Do not fix
the code until the amended ADR is approved.

This distinction prevents the spec from silently diverging from intent. Every
bug is information about which layer failed.

---

## SDD Layer Reference

Every document in `docs/` belongs to one of three SDD layers:

| Layer | Purpose | Documents |
|-------|---------|-----------|
| **Discover** | What and why — business context | `README.md`, `docs/business/` |
| **Design** | How — architecture decisions | `docs/adr/`, `docs/deployment-architecture.md`, `docs/api-specification.md`, `docs/sla.md` |
| **Task** | Execution details — verifiable contracts | `docs/tasks/` |

The Task layer governs the code. The Design layer governs the Task layer.
The Discover layer governs the Design layer. Do not skip layers.
