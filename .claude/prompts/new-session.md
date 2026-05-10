# New Session Starter — Paste This First in Every Claude Code Session

---

I'm building Fynor Agent Reliability Platform.
GitHub: https://github.com/sriramkarthick/fynor-mcp-scorecard
Python 3.11. pip install fynor.

Current phase: Phase B v0.1 — MCP check engine (ships November 2026).

Coding contract (always follow):
- Every check returns CheckResult dataclass (see fynor/checks/__init__.py)
- Use httpx, never requests
- Use rich for terminal output
- Failure codes: {TYPE}_{###}_{DESCRIPTOR} e.g. MCP_001_HIGH_LATENCY
- severity is a field on CheckResult (CRITICAL/HIGH/MEDIUM/LOW)
- Score: Security(30%) + Reliability(40%) + Performance(30%)
- CRITICAL security failure -> grade capped at D

Detailed context files (load only what this session needs):
  .claude/context/00-mission.md          <- $80M exit, phases A/B/C/D
  .claude/context/01-architecture.md     <- 5 ADRs, 3-tier architecture
  .claude/context/02-checks-catalog.md   <- all 40 checks + failure codes
  .claude/context/03-data-schemas.md     <- CheckResult code + PostgreSQL
  .claude/context/04-tech-stack.md       <- every tech decision
  .claude/context/05-build-sequence.md   <- month-by-month build plan
  .claude/context/06-intelligence-layer.md <- self-learning, ground truth
  .claude/context/07-product-interfaces.md <- CLI, SDK, REST API, MCP server
  .claude/context/08-ecosystem-protocols.md <- A2A, AG-UI, ACP
  .claude/context/09-founder-trajectory.md  <- certs, IIT Madras, Columbia
  .claude/context/10-competitive-strategy.md <- positioning, contingency

For this session I need to: [DESCRIBE YOUR SPECIFIC TASK HERE]

Context files needed for this task: [LIST WHICH ONES TO LOAD]

---
