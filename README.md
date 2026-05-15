# Fynor — AI Agent Reliability Platform

[![CI](https://github.com/sriramkarthick/fynor-reliability-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/sriramkarthick/fynor-reliability-platform/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests: 415+](https://img.shields.io/badge/tests-415%2B%20passing-brightgreen.svg)](#testing)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**The next trillion users are AI agents. Every category of software needs an agent-first rebuild.**

Fynor is the reliability platform for that rebuild. It checks whether APIs, MCP servers, and CLIs behave correctly under agent-specific workloads — not just human traffic.

```bash
pip install fynor
fynor check --target https://your-mcp-server.com/mcp --type mcp
```

```
────────────────────────────────────────────────────────────
  Target:    https://your-mcp-server.com/mcp
  Type:      MCP
  Grade:     B  (81.5/100)

  Security:    100.0/100
  Reliability:  72.0/100
  Performance:  80.0/100

  ✓ latency_p95              100  P95 latency: 340ms over 20 requests.
  ✗ error_rate                30  Error rate: 8.2% (4/50 requests failed).
  ✓ schema                   100  MCP schema valid: JSON-RPC 2.0 compliant.
  ✓ retry                    100  Correctly returned 400 on malformed request.
  ✓ auth_token               100  No leakage, 401 on missing auth, no URL secrets.
  ✓ rate_limit               100  429 + Retry-After returned on burst.
  ✓ timeout                  100  Response in 340ms (within 2s threshold).
  ✗ log_completeness           0  No audit log endpoint found.
  ✓ data_freshness           100  Timestamp found: updated_at = 2026-05-15T...
  ✓ tool_description_quality 100  All 4 tools have name + description + schema.
  ✓ response_determinism     100  3/3 probes returned identical schema.
────────────────────────────────────────────────────────────

  Fix error_rate and log_completeness to reach grade A.
```

**Checking a REST API** — 3 MCP-specific checks automatically marked N/A and excluded from scoring:

```bash
fynor check --target https://api.example.com --type rest
```

```
────────────────────────────────────────────────────────────
  Target:    https://api.example.com
  Type:      REST
  Grade:     A  (92.5/100)

  ✓ latency_p95              100  P95 latency: 120ms over 20 requests.
  ✓ error_rate               100  Error rate: 0.0% (0/50 requests failed).
  - schema                   N/A  Not applicable: MCP (JSON-RPC 2.0) only.
  - retry                    N/A  Not applicable: MCP (JSON-RPC 2.0) only.
  ✓ auth_token               100  No leakage, 401 on missing auth, no URL secrets.
  ✓ rate_limit                80  429 returned but Retry-After header missing.
  ✓ timeout                  100  Response in 120ms (within 2s threshold).
  ✓ log_completeness          60  Partial log coverage: /logs found, no fields.
  ✓ data_freshness           100  Timestamp found: updated_at = 2026-05-15T...
  - tool_description_quality N/A  Not applicable: MCP (JSON-RPC 2.0) only.
  ✓ response_determinism     100  3/3 probes returned identical schema.
────────────────────────────────────────────────────────────
```

---

## Table of Contents

- [The Problem](#the-problem)
- [Three Layers](#three-layers)
- [Installation](#installation)
- [Usage](#usage)
- [Scoring](#scoring-adr-02-locked)
- [Self-Learning Architecture](#self-learning-architecture)
- [Package Structure](#package-structure)
- [Testing](#testing)
- [Why Fynor](#why-fynor)
- [FAQ](#faq)
- [Contributing](#contributing)
- [Get a Full Audit](#get-a-full-audit)
- [License](#license)

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

### Layer 1 — Software for Agents (v0.1, available now)

11 deterministic checks. No LLM judgment. Binary pass/fail. Same input → same output, always.

| # | Check | What it catches | Interface |
|---|-------|----------------|-----------|
| 1 | `latency_p95` | P95 regression under sustained agent load | All |
| 2 | `error_rate` | Silent failure patterns over 50-request window | All |
| 3 | `schema` | MCP spec drift — JSON-RPC 2.0 envelope violations | MCP only |
| 4 | `retry` | Server crashes on malformed input (agent pipeline killer) | MCP only |
| 5 | `auth_token` | Credential leakage, missing 401, secrets in URL params | All |
| 6 | `rate_limit` | 429 + Retry-After missing — agent floods endpoint | All |
| 7 | `timeout` | Hard hang on slow response (pipeline blocker) | All |
| 8 | `log_completeness` | No structured audit trail for regulated environments | All |
| 9 | `data_freshness` | Stale data propagation — agent reasons over outdated state | All |
| 10 | `tool_description_quality` | Missing tool descriptions cause agents to select wrong tools | MCP only |
| 11 | `response_determinism` | Non-deterministic schemas break agent context windows | All |

Checks 3, 4, and 10 are MCP-specific (they validate JSON-RPC 2.0 semantics). When running against a REST, GraphQL, gRPC, WebSocket, or CLI target, they are automatically marked **N/A** and excluded from scoring.

**Interface coverage roadmap:**

| Version | Ships | Interfaces |
|---------|-------|-----------|
| v0.1 | Month 6 | MCP servers ✓ |
| v0.2 | Month 9 | REST APIs + Security |
| v0.3 | Month 12 | GraphQL + WebSocket |
| v0.4 | Month 15 | gRPC + SOAP |
| v0.5 | Month 18 | CLI tools |
| v1.0 | Month 20 | All 7 types + hosted dashboard + Agent-Ready certification |

**Agent-Ready Certification:** an interface that passes all applicable checks for 30 consecutive days earns the badge:

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

## Installation

**Requirements:** Python 3.11 or 3.12

```bash
pip install fynor
```

Verify the install:

```bash
fynor --version
```

> **Windows users:** Fynor uses Unicode characters (─, ✓, ✗) in its output.
> These display correctly in Windows Terminal and VS Code. If you use the
> legacy `cmd.exe` or an older PowerShell window, run `chcp 65001` first
> to switch to UTF-8 encoding.

---

## Usage

### Check a public MCP server

```bash
fynor check --target https://mcp.example.com/mcp --type mcp
```

### Check your own server locally

```bash
# --skip-ssrf-check is required for localhost/127.0.0.1 targets
fynor check --target http://localhost:8000/mcp --type mcp --skip-ssrf-check
```

### Check an authenticated server

```bash
# Pass the Bearer token directly
fynor check --target https://mcp.example.com/mcp --type mcp --auth-token YOUR_TOKEN

# Or export it as an environment variable (recommended — keeps tokens out of shell history)
export FYNOR_AUTH_TOKEN=YOUR_TOKEN
fynor check --target https://mcp.example.com/mcp --type mcp
```

### Check a REST API

```bash
fynor check --target https://api.example.com --type rest
```

### View check history

```bash
# All history
fynor history

# Filter to one target
fynor history --target https://mcp.example.com/mcp

# Last 20 rows
fynor history --last 20
```

### Detect patterns across history

```bash
# Requires 10+ check runs to produce meaningful output
fynor patterns
```

### JSON output (for CI/CD pipelines)

```bash
fynor check --target https://api.example.com --type rest --output json | jq .grade
```

### Context-specific scoring profiles

```bash
# security: stricter thresholds (≤1% error rate, ≤500ms P95, full determinism)
fynor check --target https://api.example.com --type mcp --profile security

# financial: SOC 2 / PCI DSS aligned thresholds
fynor check --target https://api.example.com --type mcp --profile financial
```

### Use in a GitHub Action

```yaml
# .github/workflows/agent-reliability.yml
- uses: fynor/check@v1        # ships Month 8 — use CLI wrapper until then
  with:
    target: https://your-api.com
    type: mcp
    fail-on: C                # fail CI if grade drops below C
```

Until the action ships, wrap the CLI:

```yaml
- name: Check agent reliability
  run: |
    pip install fynor
    fynor check --target https://your-api.com --type mcp --output json > result.json
    grade=$(jq -r .grade result.json)
    echo "Grade: $grade"
    [[ "$grade" == "A" || "$grade" == "B" ]] || exit 1
```

---

## Scoring (ADR-02, locked)

**Security (30%) + Reliability (40%) + Performance (30%)**

| Category | Checks | Weight |
|----------|--------|--------|
| Security | `auth_token` | 30% |
| Reliability | `error_rate`, `schema`*, `retry`*, `timeout`, `log_completeness`, `data_freshness`, `tool_description_quality`*, `response_determinism` | 40% |
| Performance | `latency_p95`, `rate_limit` | 30% |

*MCP-only checks. Marked N/A for non-MCP targets; their weight is redistributed to the remaining categories.

| Grade | Score | Meaning |
|-------|-------|---------|
| A | 90–100 | Agent-ready. Safe to use in production. |
| B | 75–89 | Minor issues. Safe with monitoring. |
| C | 60–74 | Moderate issues. Investigate before production. |
| D | 45–59 | Significant failures. Not recommended. |
| F | 0–44 | Critical failures. Do not use. |

**Security cap rule (ADR-02):** A zero score on `auth_token` caps the overall grade at D, regardless of other scores. A fast server with broken auth is not B-grade.

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

## Package Structure

```
fynor/
├── adapters/               Interface adapters (one per type — MCP, REST, …)
│   ├── base.py             BaseAdapter abstract class + SSRF validation
│   ├── mcp.py              MCP adapter (JSON-RPC 2.0) — v0.1 ✓
│   ├── rest.py             REST adapter (HTTP + JSON) — v0.2
│   ├── graphql.py          GraphQL adapter — v0.3
│   ├── grpc.py             gRPC adapter (grpc.aio) — v0.4
│   └── websocket.py        WebSocket adapter — v0.3
│
├── checks/                 11 deterministic checks per interface type
│   ├── shared.py           Shared utilities (timestamp parsing, response comparison)
│   ├── mcp/                All 11 MCP checks — v0.1 ✓ fully implemented
│   ├── rest/               REST checks — v0.2 (Month 9)
│   ├── graphql/            GraphQL introspection check — v0.3
│   ├── grpc/               gRPC reflection check — v0.4
│   ├── websocket/          WebSocket keepalive check — v0.3
│   ├── soap/               SOAP checks — v0.4
│   ├── cli_tool/           CLI tool checks — v0.5
│   └── security/           Cross-interface security checks — v0.2
│
├── intelligence/           Self-learning and pattern recognition
│   ├── pattern_detector.py Statistical engine (co-failure, drift, time signature) ✓
│   ├── failure_interpreter.py  AI Junction 1 — failure interpreter (Month 7)
│   ├── pattern_learner.py      AI Junction 2 — pattern library growth (Month 9)
│   └── ontology_updater.py     AI Junction 3 — domain rule proposals (Month 18)
│
├── api/                    Hosted service (FastAPI + DynamoDB) — Month 4 ✓
│   ├── main.py             POST /check, GET /check/{id}, GET /history, GET /health
│   ├── auth.py             HMAC-SHA256 API key authentication
│   ├── validators.py       SSRF + URL validation
│   └── middleware/         Cloudflare-aware rate limiting
│
├── certification/          Agent-Ready certification badge system — Month 6
│   └── certificate.py      Certificate data model + 30-day window evaluator
│
├── profiles.py             Check profiles: default | security | financial
├── history.py              Append-only check result log (JSONL)
├── scorer.py               Weighted grade engine (ADR-02, locked weights)
└── cli.py                  CLI entry point (click)

docs/
├── adr/                    Architecture Decision Records (locked constraints)
│   ├── ADR-01              Automation vs AI junction principles
│   ├── ADR-02              Scoring weights (30/40/30) + security cap
│   ├── ADR-03              Check taxonomy (11 checks, each with failure modes)
│   └── ADR-04              Threshold justification with academic citations
├── tasks/                  Implementation contracts for each feature area
├── api-specification.md    Hosted service REST API spec (source of truth)
├── deployment-architecture.md  AWS topology
└── business/               Financial model, market sizing, competitive moat

infra/
├── cloudflare/             Terraform for Cloudflare rate limiting + WAF
└── railway/                railway.toml for zero-config Railway deployment
```

---

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run the full test suite (415+ tests)
pytest tests/ -v

# Run only check tests
pytest tests/checks/ -v

# Run with coverage report (90% floor)
pytest --cov=fynor --cov-report=term-missing --cov-fail-under=90

# Lint
ruff check .

# Type checking (strict)
mypy fynor/ --strict
```

All three gates (lint, mypy, pytest) must pass before any commit. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full quality gate requirements.

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

## FAQ

**Do I need an API key or account to run `fynor check`?**

No. The CLI is fully open source and runs locally on your machine. No account, no registration, no internet connection to Fynor's servers required. `pip install fynor` and run immediately.

**Can I check any MCP server?**

You can check:
- Any publicly accessible MCP server (no auth required)
- Any server that accepts a standard Bearer token (`--auth-token YOUR_TOKEN`)
- Any server on your local machine (`--skip-ssrf-check`)

You cannot currently check servers that require IP allowlisting, mTLS, or non-Bearer auth schemes.

**What is a public MCP server?**

An MCP (Model Context Protocol) server is a JSON-RPC 2.0 HTTP endpoint that AI agents call to use tools. Public servers accept unauthenticated or token-authenticated requests. You can run your own with any MCP framework (e.g. `fastmcp`, `mcp-server`) and test it locally using `--skip-ssrf-check`.

**Why does my REST API still show some failures?**

The three MCP-specific checks (`schema`, `retry`, `tool_description_quality`) show **N/A** for REST targets and do not affect your grade. If your score is still low, check:
- `error_rate` — are requests returning 4xx? Authenticated endpoints get 401s counted as errors.
- `auth_token` — does your API return a clean 401 for unauthenticated requests?
- `data_freshness` — do responses include a timestamp field (e.g. `updated_at`, `created_at`)?

**Why does the `auth_token` check fail even though my server has auth?**

The check tests *how* auth is handled, not just whether it exists. It verifies: (1) no credentials appear in response bodies or URL params; (2) unauthenticated requests get a clean 401; (3) invalid tokens are rejected. A server that accepts any Bearer token, or that leaks the token in a response body, will fail this check even if it has auth.

**What does grade A mean exactly?**

Grade A (90–100) means all applicable checks passed with high scores under the conditions Fynor tested. It is a deterministic certification — it does not require AI judgment and produces the same result every time. It does not mean the server is perfect: it means it passed every agent-specific reliability check Fynor currently implements.

**Does Fynor send my data anywhere?**

No. All 11 checks run locally using `httpx`. Results are written to `~/.fynor/history.jsonl` on your machine only. The hosted API (`fynor/api/`) is a separate opt-in service — the open-source CLI does not call it.

**The checks take a long time. Is that normal?**

Yes. `error_rate` sends 50 requests; `latency_p95` sends 20. Together they dominate runtime (~50 seconds). All 11 checks run concurrently via `asyncio.gather`, so total wall time equals the slowest single check, not the sum.

**Can I run Fynor in CI/CD without the GitHub Action?**

Yes — see the [Usage](#usage) section above for a shell-based approach. Use `--output json` and parse the `grade` field.

---

## Contributing

Pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before starting — the ADR system means some changes (new checks, threshold changes, weight changes) require a proposal issue before any code is written.

To report a bug, propose a new check, or request a feature, use the issue templates:

**[→ Open an issue](https://github.com/sriramkarthick/fynor-reliability-platform/issues/new/choose)**

See [SECURITY.md](SECURITY.md) for how to report security vulnerabilities privately.

---

## Get a Full Audit

The open-source tool runs the 11 deterministic checks automatically.

For a deep manual audit — domain ontology assessment, runtime monitoring setup, compliance documentation — book 30 minutes:

**[→ Book a full audit](https://calendly.com/sriram-fynor)**

---

## License

MIT. See [LICENSE](LICENSE).

---

*Fynor Technologies — Building the AI OS layer, one check at a time.*
