# Fynor — Build Sequence

**SDD Layer:** Task  
**Governs:** All feature work, sprint planning, milestone definitions  
**Status:** Active  
**Last updated:** 2026-05-13

This document defines the month-by-month build order for Fynor. Every feature
has a designated month. Building features out of order is a scope violation —
earlier phases must be done and tested before later phases begin.

**Decision basis:** D1 (CLI-first), D4 (tight MVP Month 1-6), D9 (confirmed sequence).

---

## Phase A: CLI Foundation (Month 1–2)

**Goal:** A working pip-installable CLI that any developer can run locally.
No hosted service. No payment. No database. Just `pip install fynor` → `fynor check <url>`.

### Month 1 Deliverables

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| All 8 checks implemented | `fynor/checks/` | `pytest tests/checks/ -v` |
| Scorer with security cap | `fynor/scorer.py` | `pytest tests/test_scorer.py -v` |
| CLI: `fynor check <url>` | `fynor/cli.py` | `fynor check https://example-mcp.com` prints grade |
| CLI: `fynor history` (local JSON) | `fynor/cli.py` | History file written to `~/.fynor/history.jsonl` |
| `pip install fynor` works | `pyproject.toml` | `pip install -e .` succeeds, `fynor --help` works |
| pytest ≥ 90% coverage | `tests/` | `pytest --cov=fynor --cov-fail-under=90` |
| ruff + mypy strict clean | `fynor/` | `ruff check . && mypy fynor/ --strict` exit 0 |

### Month 2 Deliverables

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| CLI: `fynor report` (rich terminal output) | `fynor/cli.py`, `fynor/reporting.py` | `fynor report <url>` shows formatted scorecard |
| CLI: `fynor cert status <url>` (local check only) | `fynor/cli.py` | Returns current grade, no hosted call |
| README with install + quickstart | `README.md` | A developer can follow it cold and get a result |
| PyPI publish workflow | `.github/workflows/publish.yml` | `pip install fynor` works from PyPI |
| GitHub Actions CI | `.github/workflows/ci.yml` | CI passes on every PR |

**Month 2 exit criterion:** A developer who has never seen Fynor can run
`pip install fynor && fynor check https://their-mcp-server.com` and get a
letter grade within 60 seconds.

---

## Phase A2: Landing Page (Month 3)

**Goal:** fynor.tech is live with a waitlist. No functional hosted service yet —
just brand presence and email capture to build the Pro waitlist.

| Feature | Verifiable by |
|---------|--------------|
| fynor.tech landing page (static S3 + CloudFront) | Page loads in <2s globally |
| Waitlist form → EmailOctopus/ConvertKit | Form submission captured |
| "How it works" explainer | Describes 8 checks + grade system |
| Link to GitHub repo + PyPI | Both links work |

**Month 3 exit criterion:** 50+ waitlist signups from organic traffic / HN post.

---

## Phase B: Hosted Service (Month 4–5)

**Goal:** fynor.tech hosted API is live. Pro tier ($49/mo) is chargeable.
Developers who don't want to run the CLI themselves can submit a URL and
get a managed grade.

**Decision basis:** D2 (async workers), D3 (DynamoDB), D5 (FastAPI).

### Month 4 Deliverables

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| FastAPI app scaffolded | `fynor/api/main.py` | App starts, `/health` returns 200 |
| `POST /check` endpoint | `fynor/api/routes/checks.py` | Returns `job_id` within 1s |
| ECS Fargate task (orchestrates all 8 checks in-process via `asyncio.gather`) | `infrastructure/terraform/ecs.tf` | Task runs, all 8 checks execute concurrently |
| ECS task definition + ECR image | `infrastructure/terraform/ecr.tf`, `Dockerfile` | `docker build` succeeds; image pushed to ECR |
| DynamoDB table provisioned | `infrastructure/terraform/dynamodb.tf` | Table exists, PK=target_hash, SK=timestamp |
| Check results written to DynamoDB | `fynor/api/storage.py` | Results queryable within 5s of completion |
| `GET /check/{job_id}` polling endpoint | `fynor/api/routes/checks.py` | Returns result or `{"status": "pending"}` |
| Stripe integration (Pro tier) | `fynor/api/billing.py` | Test payment succeeds |

### Month 5 Deliverables

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| API key auth (HMAC-SHA256 hash stored) | `fynor/api/auth.py` | Unauthenticated requests return 401 |
| `GET /history` endpoint | `fynor/api/routes/history.py` | Returns last N runs for target |
| Rate limiting by tier | `fynor/api/middleware/rate_limit.py` | Pro: 12 runs/hr enforced |
| Webhook delivery (check.completed) | `fynor/api/webhooks.py` | Webhook fires within 30s of check completion |
| Staging environment live | `infrastructure/` | Staging API endpoint responds |
| Production deploy | `infrastructure/` | fynor.tech/api responds |

**Month 5 exit criterion:** First paying Pro customer ($49) completes a check
run via the hosted API and receives a webhook.

---

## Phase B2: Certification (Month 6)

**Goal:** The Agent-Ready certificate is live. Badges render on CloudFront.
The 30-day certification window is running.

**Decision basis:** D8 (DynamoDB TTL + EventBridge cron).

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| `GET /cert/{id}` endpoint | `fynor/api/routes/certs.py` | Returns cert with grade, issued_at, valid_until |
| Badge SVG generation | `fynor/api/badges.py` | SVG renders correctly for each grade |
| CloudFront badge CDN | `infrastructure/terraform/cloudfront.tf` | Badge URL returns SVG in <200ms globally |
| EventBridge daily cron (02:00 UTC) | `infrastructure/lambdas/cert_evaluator.py` | Runs daily, updates cert_status in DynamoDB |
| 30-day window evaluation logic | `fynor/certification/evaluator.py` | 30 consecutive passing days → CERTIFIED |
| FYNOR_INFRA_ERROR handling | `fynor/certification/evaluator.py` | Infrastructure outage days excluded from 30-day count |
| Cert suspension on failure | `fynor/certification/evaluator.py` | One failing day within window → SUSPENDED |
| `GET /targets` endpoint | `fynor/api/routes/targets.py` | Lists all registered targets with cert status |

**Month 6 exit criterion:** A server that passes checks for 30 consecutive days
receives an `Agent-Ready` badge URL that renders correctly in a GitHub README.

---

## Phase C: AI Junctions (Month 7–9)

**Goal:** The intelligence layer activates. Human-gated AI junctions come online.
No junction is on the critical path for check delivery (ADR-01 governing rule).

### Month 7 — Junction 1: Failure Interpretation Agent

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| Claude API integration | `fynor/intelligence/failure_interpreter.py` | `interpret_failure()` returns `FailureInterpretation` |
| Async interpretation queue | `infrastructure/lambdas/interpreter.py` | Interpretation delivered within 24h of check |
| Human review gate | `fynor/api/routes/interpretations.py` | Interpretation status: pending → approved → published |
| Email/webhook notification | `fynor/api/notifications.py` | User notified when interpretation is ready |
| Fallback if Claude API down | `fynor/intelligence/failure_interpreter.py` | Status = "pending", retried within 24h |

### Month 8 — REST Adapter (v0.2)

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| `BaseAdapter` interface | `fynor/adapters/base.py` | All 8 checks run via adapter |
| `MCPAdapter` (refactored from current) | `fynor/adapters/mcp.py` | Existing tests still pass |
| `RESTAdapter` | `fynor/adapters/rest.py` | `fynor check --type rest <url>` works |
| Adapter auto-detection | `fynor/adapters/detector.py` | Correct adapter chosen without `--type` flag |

### Month 9 — Junction 2: Pattern Learning

| Feature | File(s) | Verifiable by |
|---------|---------|--------------|
| Pattern detector writes to `patterns.jsonl` | `fynor/intelligence/pattern_detector.py` | Patterns appear after 10+ runs |
| `GET /patterns` endpoint | `fynor/api/routes/patterns.py` | Returns detected patterns |
| Pattern proposal → human approval | `fynor/api/routes/patterns.py` | Status: proposed → approved → active |
| Approved patterns feed ADR-03 amendment | `docs/adr/ADR-03-check-taxonomy.md` | New failure mode documented |

**Month 9 exit criterion:** At least one pattern is detected, reviewed by a human,
approved, and documented as a new failure mode in ADR-03.

---

## What Does Not Exist Yet (Month 10+)

- Phase C (AI OS): Ground Truth Database, domain ontology, Junction 3 → Month 18+
- Phase D (Company Brain): Domain standard, federated GT → Month 24+
- SDK (Python Month 14, TypeScript Month 16, Go Month 20)
- SOC 2 Type II → Month 24
- Enterprise tier → Month 18+

Do not implement these. They are not in scope until their designated month.

---

## Scope Violation Detection

If a PR introduces code that belongs to a later month, it is a scope violation.
Common examples:

| Code you're about to write | It belongs to | If you're in |
|---------------------------|--------------|-------------|
| Ground Truth DB schema | Month 18+ | Any earlier month |
| Junction 3 (domain ontology) | Month 18+ | Any earlier month |
| GraphQL API | Not planned | — |
| ML model training | Not planned | — |
| Multi-tenant DB isolation | Month 18+ | Any earlier month |

Flag scope violations before implementing. Ask: "Is this in the build sequence?"
If not, it should not exist.
