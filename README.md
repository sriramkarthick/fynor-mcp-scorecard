# Fynor — AI Agent Reliability Platform

**The next trillion users are AI agents. Every category of software needs an agent-first rebuild.**

Fynor is the reliability platform for that rebuild. It checks whether APIs, MCP servers, and CLIs behave correctly under agent-specific workloads — not just human traffic.

```bash
pip install fynor
fynor check --target https://your-mcp-server.com/mcp --type mcp
```

```
──────────────────────────────────────────────────────────────
  Target:    https://your-mcp-server.com/mcp
  Type:      MCP
  Grade:     B  (81.5/100)

  Security:    100.0/100
  Reliability:  72.0/100
  Performance:  80.0/100

  ✓ latency_p95          100  P95 latency: 340ms over 20 requests.
  ✗ error_rate             30  Error rate: 8.2% (4/50 requests failed).
  ✓ schema               100  MCP schema valid: JSON-RPC 2.0 compliant.
  ✓ retry                100  Correctly returned 400 on malformed request.
  ✓ auth_token           100  No leakage, 401 on missing auth, no URL secrets.
  ✓ rate_limit           100  429 + Retry-After returned on burst.
  ✓ timeout              100  Response in 340ms (within 2s threshold).
  ✗ log_completeness       0  No audit log endpoint found.
──────────────────────────────────────────────────────────────
```

---

## The Problem

APIs, MCP servers, and CLIs were built for humans:
- Rate limits designed for 10 requests/minute, not 10,000
- Error messages readable by humans, not parseable by machines
- Tolerant parsing forgiving enough for a human to interpret
- Interactive workflows that assume a human clicks the next step

AI agents break every one of these assumptions. A single failure at call #23 in a 50-step pipeline corrupts everything before it. Agents cannot read an error message and adapt. Silent failures are invisible until production.

**No existing tool tests software against agent-specific failure modes.** Postman, Datadog, Prometheus — all built for human-facing software. None ask: *"Does this MCP server behave correctly when an AI agent calls it 10,000 times per minute?"*

---

## Three Layers

### Layer 1 — Software for Agents (Phase B, now)

8 deterministic checks. No LLM judgment. Binary pass/fail. Every interface type.

| # | Check | What it catches |
|---|-------|----------------|
| 1 | `latency_p95` | P95 regression under sustained agent load |
| 2 | `error_rate` | Silent failure patterns over 50-request window |
| 3 | `schema` | MCP spec drift — JSON-RPC 2.0 envelope violations |
| 4 | `retry` | Server crashes on malformed input (agent pipeline killer) |
| 5 | `auth_token` | Credential leakage, missing 401, secrets in URL params |
| 6 | `rate_limit` | 429 + Retry-After missing — agent floods endpoint |
| 7 | `timeout` | Hard hang on slow response (pipeline blocker) |
| 8 | `log_completeness` | No structured audit trail for regulated environments |

**Interface coverage (version roadmap):**

| Version | Ships | Interfaces |
|---------|-------|-----------|
| v0.1 | Month 6 | MCP servers |
| v0.2 | Month 9 | REST APIs + Security |
| v0.3 | Month 12 | GraphQL + WebSocket |
| v0.4 | Month 15 | gRPC + SOAP |
| v0.5 | Month 18 | CLI tools |
| v1.0 | Month 20 | All 7 types + hosted dashboard + Agent-Ready certification |

**Agent-Ready Certification:** an interface that passes all checks for 30 consecutive days earns the badge:

```markdown
[![Fynor Agent-Ready](https://fynor.tech/badge/your-id)](https://fynor.tech/cert/your-id)
```

### Layer 2 — AI OS for Companies (Phase C, 2027+)

Continuous monitoring of AI agent decisions against domain ontology rules.

Every company deploying AI agents faces the same problem: there is no infrastructure to record what the agent decided, verify whether the decision was correct for the domain, or turn isolated AI decisions into a closed-loop learning system.

Fynor is the AI OS layer that makes this possible:

```
AI agent makes decision
  → Runtime monitor checks against domain ontology
  → Decision recorded in decision_log.jsonl
  → Violation flagged → domain expert reviews → ground truth record created
  → "Our AI complied with FINRA rule 4370 in 99.2% of decisions last quarter"
  → Audit trail queryable by regulators
```

### Layer 3 — Company Brain (Phase D, 2030+)

The domain ontology packaged as an open standard: a versioned, subscribable Company Brain.

Company knowledge lives in Slack, email, and people's heads. When key people leave, the knowledge leaves. AI agents cannot execute knowledge they cannot access.

The Company Brain is the solution: structured company know-how, version-controlled, queryable by AI agents, growing with every audit.

---

## Scoring (ADR-02, locked)

**Security (30%) + Reliability (40%) + Performance (30%)**

| Grade | Score | Meaning |
|-------|-------|---------|
| A | 90–100 | Agent-ready. Safe to use in production. |
| B | 75–89 | Minor issues. Safe with monitoring. |
| C | 60–74 | Moderate issues. Investigate before production. |
| D | 45–59 | Significant failures. Not recommended. |
| F | 0–44 | Critical failures. Do not use. |

**Security cap rule:** A zero score on `auth_token` caps the overall grade at D, regardless of other scores. A fast server with broken auth is not B-grade.

---

## Self-Learning Architecture

Every check run writes to `~/.fynor/history.jsonl`. Over time, Fynor learns:

```
Check run → history.jsonl
    ↓
Pattern Detector (statistical, no AI):
  · Co-failure correlation — which checks fail together?
  · Latency drift         — is P95 trending upward over 30 days?
  · Time signature        — do failures cluster at specific hours?
    ↓ anomaly detected
AI Agent Junction 1 — Failure Interpretation Agent
  · Reads failure + history + pattern library
  · Proposes specific remediation
  ↓ human approves
Pattern Library (confirmed entries)
    ↓ 50+ confirmed entries of same type
AI Agent Junction 2 — Pattern Learning Agent
  · Proposes new detection function for pattern_detector.py
  ↓ human approves
Updated Pattern Detector
    ↓ (Phase C)
AI Agent Junction 3 — Ontology Update Agent
  · Proposes new domain ontology rule
  ↓ domain expert labels it
Ground Truth Database (the moat)
```

**Governing rule: AI proposes. Human approves. Automation executes.**

---

## Installation

```bash
pip install fynor
```

**Requirements:** Python 3.11+

**Run your first check:**
```bash
fynor check --target http://localhost:8000/mcp --type mcp
```

**Check history and patterns:**
```bash
fynor history --target http://localhost:8000/mcp
fynor patterns
```

**JSON output (for CI/CD):**
```bash
fynor check --target https://api.example.com --type rest --output json
```

**GitHub Action:**
```yaml
# .github/workflows/agent-reliability.yml
- uses: fynor/check@v1        # ships Month 8
  with:
    target: https://your-api.com
    type: mcp
    fail-on: C                # fail CI if grade drops below C
```

---

## Package Structure

```
fynor/
├── adapters/               Interface adapters (one per type — MCP, REST, …)
│   ├── base.py             BaseAdapter abstract class
│   ├── mcp.py              MCP adapter (JSON-RPC 2.0) — v0.1
│   └── rest.py             REST adapter (HTTP + JSON) — v0.2
│
├── checks/                 8 deterministic checks per interface type
│   ├── mcp/                MCP checks (v0.1 — all 8 implemented)
│   ├── rest/               REST checks (v0.2 — Month 9)
│   ├── graphql/            GraphQL checks (v0.3 — Month 12)
│   ├── grpc/               gRPC checks (v0.4 — Month 15)
│   ├── websocket/          WebSocket checks (v0.3 — Month 12)
│   ├── soap/               SOAP checks (v0.4 — Month 15)
│   ├── cli_tool/           CLI checks (v0.5 — Month 18)
│   └── security/           Cross-interface security checks (v0.2)
│
├── intelligence/           Self-learning and pattern recognition
│   ├── pattern_detector.py Statistical engine (co-failure, drift, time signature)
│   ├── failure_interpreter.py  AI Junction 1 — root cause + remediation (Month 7)
│   ├── pattern_learner.py      AI Junction 2 — pattern library growth (Month 9)
│   └── ontology_updater.py     AI Junction 3 — domain rule proposals (Month 18)
│
├── certification/          Agent-Ready certification badge system (Month 12)
│   └── certificate.py      Certificate data model
│
├── monitoring/             Runtime monitoring layer / AI OS (Phase C, 2027+)
│   └── decision_logger.py  AI agent decision recorder
│
├── brain/                  Company Brain standard (Phase D, 2030+)
│   └── schema.py           OntologyFile + OntologyRuleEntry data model
│
├── ontology/               Domain ontology storage (Phase C)
├── report/                 Report generation
├── history.py              Append-only check result log (JSONL)
├── scorer.py               Weighted grade engine (ADR-02)
└── cli.py                  CLI entry point
```

---

## Why Fynor

**Existing tools were built for humans, not agents.**

| Tool | What it measures | What it misses |
|------|-----------------|----------------|
| Postman | Does the API respond? | Does it respond correctly at 10,000 req/min? |
| Datadog | Latency, uptime | Agent-specific failure modes |
| PromptFoo | LLM output quality | Interface reliability under agent load |
| LangSmith | Token cost, latency | Schema drift, auth handling, rate limit compliance |
| Nothing | MCP server reliability | Everything |

Fynor is the first reliability platform built for how AI agents actually use software.

---

## Get a Full Audit

The open-source tool runs the 8 deterministic checks automatically.

For a deep manual audit — domain ontology assessment, runtime monitoring setup, compliance documentation — book 30 minutes:

**[→ Book a full audit](https://calendly.com/sriram-fynor)**

---

## License

MIT. See [LICENSE](LICENSE).

---

*Fynor Technologies — *Building the AI OS layer, one check at a time.*
