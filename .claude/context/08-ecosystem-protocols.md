# Ecosystem Protocols — A2A, AG-UI, ACP + Fynor's Position

## The Protocol Landscape (as of May 2026)

Four protocols now govern how AI agents communicate:

1. MCP  (Model Context Protocol)  — Anthropic — agent-to-tool
2. A2A  (Agent to Agent)          — Google    — agent-to-agent
3. AG-UI (Agent-UI Protocol)      — community — agent-to-frontend
4. ACP  (Agent Communication Protocol) — IBM  — agent-to-enterprise-system

Fynor audits interfaces built on ALL four.
MCP is the wedge (highest adoption). The others are the expansion.

---

## Protocol 1: MCP (Model Context Protocol) — Fynor's Primary Wedge

Origin: Anthropic
Status: 97M monthly downloads, April 2026. 78% enterprise adoption. 9,400+ servers.
Role: agent-to-tool communication (how an agent accesses APIs, databases, CLIs)

What it is:
  A standardized protocol for AI agents to call external tools and data sources.
  MCP servers expose "tools" (functions agents can call) and "resources" (data agents can read).
  Every enterprise deploying AI agents is deploying MCP servers.

What Fynor does with MCP:
  1. Audits MCP servers (8 checks) — does this server behave correctly under agent load?
  2. IS an MCP server (5 tools) — agents call Fynor to audit other tools

Why MCP is the wedge:
  - Fastest-growing integration standard in enterprise AI
  - Zero dedicated reliability tooling as of May 2026
  - Every MCP server deployment is a potential Fynor customer
  - First-mover advantage = 18+ months before any competitor enters this niche

MCP-specific agent failure modes Fynor catches:
  - Schema drift at call #847 (not detectable by spot-checking)
  - Rate limit absent under 10K req/min burst
  - Auth token leaked in response headers (agents log all headers)
  - Timeout hang (agent pipeline blocks indefinitely)

---

## Protocol 2: A2A (Agent to Agent) — Google

Origin: Google (released early 2026)
Role: how one AI agent communicates with another AI agent
Status: growing adoption in enterprise multi-agent systems

What it is:
  Standardizes how agents discover each other, delegate tasks, and share context.
  A2A server = an agent that can receive tasks from other agents.
  A2A client = an agent that delegates tasks to other agents.

Why it matters for Fynor:
  Every A2A server is an agent-facing interface.
  A2A servers have the same failure modes as MCP servers — plus new ones:
  - Delegation loop detection (agent A sends to B sends back to A)
  - Context payload size limits (A2A passes full context between agents)
  - Task cancellation propagation (cancel must flow through the chain)
  - Result schema consistency (downstream agent expects specific output format)

Fynor's A2A position:
  Phase B v2.0 (post Month 20): add A2A server checks as 8th interface type.
  Failure codes prefix: A2A_###
  First check: A2A_001_DELEGATION_LOOP — detect circular delegation patterns

Do not build A2A checks until v1.0 ships (Month 20).
Reason: MCP is established standard. A2A is still maturing. Watch adoption quarterly.

---

## Protocol 3: AG-UI (Agent-UI Protocol) — Community

Origin: open-source community initiative (2026)
Role: how AI agents communicate with frontend UIs (streaming, events, state updates)
Status: early adoption; primarily in consumer-facing AI applications

What it is:
  Standardizes the event stream between an AI agent backend and a web frontend.
  Defines event types: text chunks, tool calls, state updates, error signals.
  An AG-UI server is any backend that streams agent output to a frontend.

Why it matters for Fynor:
  AG-UI servers are agent-facing interfaces with specific failure modes:
  - Event ordering guarantees (frontend renders in wrong sequence)
  - Reconnection on stream drop (agent output lost mid-response)
  - Binary frame handling (file uploads embedded in event stream)
  - Backpressure when frontend is slow (agent sends faster than UI renders)

These are IDENTICAL to WebSocket checks (WSS_001-004) — same underlying pattern.
AG-UI failures cause: broken UI state, lost agent output, corrupted streaming responses.

Fynor's AG-UI position:
  Phase B v2.0 (post Month 20): AG-UI check module.
  Implementation: reuse WebSocket check logic with AG-UI event schema validation.
  Failure codes prefix: AGUI_###

Do not build AG-UI checks until community adoption is confirmed (>10K weekly downloads).

---

## Protocol 4: ACP (Agent Communication Protocol) — IBM

Origin: IBM (2026)
Role: how AI agents integrate with enterprise systems (ERP, CRM, legacy infrastructure)
Status: enterprise-only; targeted at Fortune 500 companies using IBM infrastructure

What it is:
  Enterprise-grade protocol for AI agents to call mainframe systems, ERP (SAP, Oracle),
  and legacy enterprise services that predate REST APIs.
  ACP bridges modern AI agents with 40-year-old enterprise infrastructure.

Why it matters for Fynor:
  ACP servers are agent-facing interfaces in the most regulated environments:
  - Banking core systems
  - Healthcare mainframes
  - Government infrastructure
  These are EXACTLY Phase C's target clients.

ACP-specific failure modes Fynor would catch:
  - Message format validation (ACP uses XML/EDI payloads — malformed = silent rejection)
  - Transaction atomicity (enterprise systems require ACID — agents must not assume eventual consistency)
  - Authentication token format (enterprise systems use proprietary auth formats)
  - Retry semantics (enterprise systems often reject duplicate transactions by design)

Fynor's ACP position:
  Phase C enterprise expansion (Year 4-5, 2030-2031).
  ACP clients = regulated enterprises with $150K-300K/year budget.
  This is Phase C Enterprise+ territory.
  Build ACP checks when first enterprise client requests it.

---

## How Fynor Positions Across All Four Protocols

| Protocol | Status       | Fynor Check Module | Timeline    | Priority |
|----------|--------------|--------------------|-------------|----------|
| MCP      | Live (97M DL)| checks/mcp/ (8 chks)| v0.1 Month 6| FIRST    |
| REST     | Live         | checks/rest/ (6 chks)| v0.2 Month 9| SECOND   |
| A2A      | Growing      | checks/a2a/ (future)| v2.0+       | WATCH    |
| AG-UI    | Early        | checks/agui/ (future)| v2.0+      | WATCH    |
| ACP      | Enterprise   | checks/acp/ (future)| Phase C Year 4| DEMAND |

## The Single Most Important Insight About Protocols

Every new AI agent communication protocol creates a new category of interfaces
that were NOT built for agent-scale reliability.

Every new protocol = new Fynor check module = new revenue opportunity.

The check engine architecture (independent checkers, same CheckResult contract)
was designed for this. Adding a new protocol = adding one folder with check files.
The infrastructure, scoring, reporting, and distribution are already built.

MCP today. A2A/AG-UI tomorrow. ACP for enterprise.
Fynor's architecture grows with the protocol ecosystem — without re-architecting.

## Quarterly Protocol Monitoring

Check these signals every quarter:
  MCP: download counts at npmjs.com/package/@modelcontextprotocol/sdk
  A2A: GitHub stars on google/A2A repo; enterprise blog posts mentioning A2A
  AG-UI: weekly npm downloads; mentions in frontend AI frameworks
  ACP: IBM announcements; Fortune 500 AI deployment case studies

If A2A reaches 50M downloads/month: accelerate A2A check module to next version.
If AG-UI reaches 10K weekly npm downloads: add AGUI checks to roadmap.
If ACP client inquiry arrives: scope ACP pilot; price at $10K+ for enterprise.
