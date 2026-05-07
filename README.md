# fynor-mcp-scorecard

**Run 8 reliability checks on any MCP server in under 60 seconds.**

For teams deploying AI agents on the MCP infrastructure, who need a fast audit before production. Catches configuration errors, auth failures, schema violations, and latency regressions before they become production incidents.

```bash
pip install mcp-scorecard
mcp-scorecard check https://your-mcp-server/endpoint
```

> **Status:** Active development. First release: November 2026.

---

## What it checks

| Check | What it catches |
|-------|----------------|
| Response time (P95) | Latency regressions under load |
| Error rate (24h rolling) | Silent failure patterns |
| MCP schema validation | Spec compliance drift |
| Retry behavior | Crash-on-transient-failure bugs |
| Auth token handling | Credential exposure |
| Rate limit compliance | Runaway request patterns |
| Timeout handling | Hard hangs vs. graceful degradation |
| Log completeness | Missing audit trail |

---

## Why this exists

Every MCP server failure costs 2–8 hours of debugging and risks AI agent incidents in production. Existing observability tools measure latency and errors. None of them checks whether your MCP server is *correct* — schema-compliant, auth-safe, and gracefully degrading under failure conditions.

This tool checks correctness, not just availability.

---

## Who builds this

[Fynor Technologies](https://fynor.tech) — AI reliability auditing for MCP infrastructure. Building the ground truth standard for AI agent correctness.

---

## Roadmap

- [ ] v0.1 — CLI tool, 8 checks, public endpoint support (November 2026)
- [ ] v0.2 — Local/private endpoint support via tunnel (December 2026)
- [ ] v1.0 — GitHub Action + hosted web UI (Q1 2027)
- [ ] v2.0 — Domain ontology checks for FinTech and healthcare-adjacent AI agents
