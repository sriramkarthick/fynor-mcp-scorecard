# Fynor Agent Reliability Platform — Claude Code Context

## What this project is
AI agent reliability platform. Checks every REST, GraphQL, gRPC, WebSocket, SOAP,
MCP, and CLI interface for agent-specific failure modes. Built in Python.

## Current phase
Phase B v0.1 — building MCP check engine (ships Month 6 = November 2026)

## Coding contract (follow always, no exceptions)
- Every check returns `CheckResult` dataclass — see fynor/checks/__init__.py
- Use `httpx`, never `requests`
- Use `rich` for all terminal output
- One pytest test per check file, in tests/ mirroring checks/ structure
- Failure codes format: `{TYPE}_{###}_{DESCRIPTOR}` e.g. MCP_001_HIGH_LATENCY
- Severity is a field on CheckResult (CRITICAL / HIGH / MEDIUM / LOW)

## Score aggregator weights (locked — ADR-02, do not change without new ADR)
Security checks:     30% of total score
Reliability checks:  40% of total score
Performance checks:  30% of total score
Grade: 90-100=A, 75-89=B, 60-74=C, 45-59=D, 0-44=F
CRITICAL security failure -> hard cap at grade D regardless of other scores

## Where to find detailed context (load only what the task needs)

| Topic                               | File                                       |
|-------------------------------------|--------------------------------------------|
| Mission, exit goal, phases A/B/C/D  | .claude/context/00-mission.md              |
| Architecture, 5 ADRs, tiers         | .claude/context/01-architecture.md         |
| All 40 checks + failure codes       | .claude/context/02-checks-catalog.md       |
| CheckResult schema + DB schemas     | .claude/context/03-data-schemas.md         |
| Every tech decision + reason        | .claude/context/04-tech-stack.md           |
| Month-by-month build plan           | .claude/context/05-build-sequence.md       |
| Self-learning, ground truth, moat   | .claude/context/06-intelligence-layer.md   |
| CLI, SDK, REST API, MCP server      | .claude/context/07-product-interfaces.md   |
| A2A, AG-UI, ACP protocols           | .claude/context/08-ecosystem-protocols.md  |
| Founder path, certs, IIT, Columbia  | .claude/context/09-founder-trajectory.md   |
| Competitive positioning, contingency| .claude/context/10-competitive-strategy.md |

## Reusable prompts (no re-explaining per session)

| Task                    | File                            |
|-------------------------|---------------------------------|
| Start any new session   | .claude/prompts/new-session.md  |
| Add a new check         | .claude/prompts/new-check.md    |
| Write tests for a check | .claude/prompts/write-tests.md  |
| Review check quality    | .claude/prompts/review-check.md |

## Repository
GitHub: https://github.com/sriramkarthick/fynor-mcp-scorecard
PyPI:   pip install fynor
Site:   scorecard.fynor.dev (Month 9)
