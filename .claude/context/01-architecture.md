# Architecture — Fynor Agent Reliability Platform

## System Architecture: Three Tiers

TIER 3 — INTELLIGENCE LAYER (Phase C, Month 18+)
  Domain Ontology Engine + Ground Truth DB + Human Sampling Loop
  Question answered: "Was the agent CORRECT for this domain?"

TIER 2 — PLATFORM LAYER (Phase B, Month 6+)
  Check Engine + Score Aggregator + Report Generator
  Question answered: "Did the interface BEHAVE correctly under agent conditions?"

TIER 1 — INTERFACE LAYER (Phase B, Month 6+)
  CLI + Python SDK + REST API + MCP Server + GitHub Action
  Question answered: "How does a developer or agent TALK to Fynor?"

Each tier is independently shippable.
Tier 1+2 = Phase B (v0.1 to v1.0). Tier 3 = Phase C.

## Check Engine Design (Core of Tier 2)

Input:  AuditRequest(url, type, config, domain)
Output: AuditResult(results[], score, grade, report_url)

Design rules (never violate):
- Protocol Detector routes AuditRequest to correct checker module
- Each checker is INDEPENDENT — shares zero state with any other checker
- Every checker returns the same CheckResult dataclass (see 03-data-schemas.md)
- Security checker runs cross-cutting on ALL interface types
- Checkers are designed to run in parallel (Phase C concurrent audit optimization)
- Adding a new checker = add one file + register it. Zero changes to anything else.

## Score Aggregator Logic (ADR-02 — locked)

Bucket weights:
  Security    (30%): avg score of all security checks run
  Reliability (40%): avg score of error rate, retry, timeout, auth, schema, log checks
  Performance (30%): avg score of response time, rate limit, pagination checks

Total = (security_avg x 0.30) + (reliability_avg x 0.40) + (performance_avg x 0.30)

Severity multipliers (applied before bucket averaging):
  CRITICAL = 0.0  -> zero score for the check, hard fail
  HIGH     = 0.4  -> 40% of check score carries through
  MEDIUM   = 0.7  -> 70% of check score carries through
  LOW      = 1.0  -> full score, minor issue

Hard rule: CRITICAL severity in ANY security check -> entire audit capped at grade D.
Rationale: one critical security hole cannot be averaged away by good performance scores.

Grade boundaries:
  90-100 = A (Agent-ready)
  75-89  = B (Minor issues, usable)
  60-74  = C (Reliability concerns)
  45-59  = D (Not recommended for production agents)
  0-44   = F (Do not connect any agent to this interface)

## Architecture Decision Record — All 5 ADRs (locked)

ADR-01: CheckResult severity field
  DECISION: severity as a typed field (Severity enum) on CheckResult dataclass
  REJECTED: embedding severity in failure_code string prefix
  REASON: enables score aggregator to apply multipliers without string parsing;
          enables filtering by severity without regex; type-safe

ADR-02: Scoring model
  DECISION: 30/40/30 weighted by category (Security/Reliability/Performance)
  REJECTED: equal weight per check (each of 40 checks = 2.5 points)
  REASON: security failure is categorically worse than slow P95;
          weighted model reflects real risk; harder to game with good perf scores

ADR-03: Phase B hosting
  DECISION: hosted from day one at scorecard.fynor.dev
  REJECTED: local-only CLI for Phase B
  REASON: shareable report URL is a viral growth mechanic for developer tools;
          "here's my audit score" shared on Twitter = organic distribution
  Stack: Vercel (frontend) + Railway (FastAPI) + Supabase (PostgreSQL)
  Cost: $5-7/month total at Phase B scale

ADR-04: Phase C multi-tenancy
  DECISION: start with PostgreSQL Row-Level Security (RLS)
  MIGRATE TO: dedicated RDS instance per enterprise client on compliance demand
  REJECTED: DB-per-tenant from day one (too expensive); single schema no isolation (insecure)
  REASON: start cheap, migrate when first enterprise client's auditor demands full isolation
  RLS policy: client_id = current_setting('app.current_client_id')::UUID

ADR-05: MCP server timing
  DECISION: Fynor-as-MCP-server ships Month 12 with v1.0 (polished)
  REJECTED: Month 6 with v0.1 (rushed)
  REASON: the MCP meta-play is Fynor's primary differentiator;
          it must be production-quality when it ships;
          rushing it risks the most strategic feature

## Automation Spine (Phase A — deterministic delivery layer)

Rule: deterministic processes run on automation rail;
      AI agents handle ONLY ambiguity and judgment calls.

Automation Spine components:
  IaC Generation:    Terraform / AWS CDK (reproducible infrastructure)
  CI/CD Pipeline:    GitHub Actions + checkov/tfsec (security-checked deployment)
  Policy Guardrails: AWS SCPs + Config Rules (drift prevention)
  Drift Detection:   Lambda + Step Functions (continuous state monitoring)
  Client Reporting:  EventBridge + Lambda (automated engagement reporting)

Three AI Agent Junctions — human review gate REQUIRED at each:
  1. Requirements Intake Agent  -> triggered on new client onboarding
                                -> human reviews before delivery begins
  2. Architecture Design Agent  -> triggered on infrastructure scoping
                                -> human reviews before proposal sent
  3. Anomaly Triage Agent       -> triggered on production incident detection
                                -> human reviews before remediation starts

Every agent junction is a judgment point, not a process point.
Processes are deterministic. Judgment is AI-assisted with human gate.

## Self-Learning Loop — Full Flow

Phase B loop (aggregate learning from check_results):
  Audit runs -> results stored in PostgreSQL
  Weekly batch job -> computes failure_patterns table
  Pattern published: "87% of MCP servers fail MCP_006 (rate limit absent)"
  Stat appears in README -> HN post -> organic traffic
  More audits -> richer patterns -> stronger content -> more users

Phase C loop (domain learning from ground_truth_labels):
  Runtime monitor flags agent decision outside ontology tolerance
  Domain expert receives: input, agent_decision, rule violated
  Expert records verdict in ground_truth_labels (CORRECT/INCORRECT)
  pgvector similarity: "this failure looks like gt-2028-042"
  Auto-suggest verdict to next expert for similar case
  Expert review time drops ~60% as database grows
  Pattern library updated -> next audit catches this pattern automatically
  More clients -> more labels -> faster reviews -> more clients (network effect)

## Pattern Recognition Examples

Phase B (aggregate, from check_results table):
  "87% of MCP servers fail MCP_006 (rate limit absent)" -> HN post stat -> traffic
  "REST APIs serving >10K req/min fail schema stability 4x more" -> new check idea
  "Auth token failures spike at 90-day intervals" -> blog post + auto-remediation candidate
  "GraphQL APIs with introspection enabled drift schemas 2x more" -> SEC check idea

Phase C (domain-specific, from ground_truth_labels):
  Compliance failure: "FinTech agent approves >$50K transaction without flag in 3/5 audits"
    -> new domain rule added to fintech_trading.json
  Healthcare: "Agent surfaces PII in error logs"
    -> HIPAA rule added to healthcare_clinical.json
  gRPC chain: "Trading agent deadline not propagated through gRPC service chain"
    -> confirms GRPC_003 severity upgrade to CRITICAL
  Auth rotation: "Credentials silently fail after 90-day expiry"
    -> auto-remediation candidate: "rotate on 60-day schedule"

## MCP Meta-Play (ADR-05 — Month 12, polished)

Strategic importance: Fynor checks MCP servers AND IS ITSELF an MCP server.

What this enables:
- Claude can call Fynor. LangChain agents can call Fynor. CrewAI agents can call Fynor.
- Any AI agent can audit the APIs it uses — without a human involved.
- Fynor becomes part of every agent's self-check loop.
- Distribution multiplier: every AI agent deployment = potential Fynor user.

5 tools Fynor exposes as MCP server:
  run_audit(url, type, domain)                -> AuditResult
  get_remediation(failure_code)               -> specific fix string
  compare_audits(audit_id_before, after)      -> diff of what changed
  get_audit_status(audit_id)                  -> progress of running audit
  list_failure_patterns(domain, top_n)        -> common patterns for vertical

The meta-play: the tool that CHECKS MCP servers IS an MCP server.
An AI agent can audit another AI agent's infrastructure using MCP.
No existing tool does this. This is the demo that wins conferences.

## Full System Flow (request to report)

1. Developer calls: fynor run --url X --type rest
   OR AI agent calls: run_audit(url=X, type="REST")
   OR CI/CD runs:     uses: fynor/check@v1

2. Interface Layer receives AuditRequest, passes to Check Engine

3. Check Engine: Protocol Detector routes to REST checker module
   Security checker runs in parallel on same request

4. Each checker returns CheckResult with score 0-100 + severity + failure_code + remediation

5. Score Aggregator: applies severity multipliers, computes 30/40/30 weighted total

6. Report Generator: produces terminal output (rich) + JSON + shareable HTML URL

7. If Phase C domain specified: Ontology Evaluator compares agent decisions against
   domain rules (fintech_trading.json) -> flags violations -> queues for human review

8. Human expert reviews flagged decision -> verdict stored in ground_truth_labels
   -> pgvector embedding stored -> similarity index updated -> next audit smarter
