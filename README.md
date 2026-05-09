# Fynor Agent Reliability Platform

**The first reliability platform built for how AI agents use software.**

Every API, MCP server, and CLI was built for humans. AI agents use them at machine speed,
autonomously, without a human to catch failures. Fynor checks whether your interfaces
are agent-ready — not just available, but correct under agent-specific load patterns.

```bash
pip install fynor
fynor check --target https://your-api.com --type rest
fynor check --target https://your-mcp.com --type mcp
fynor check --target grpc://your-service:443 --type grpc
fynor check --target "your-cli --help" --type cli
```

> **Status:** Active development. v0.1 ships November 2026.  
> [Book a reliability audit](https://cal.com/sriram-fynor) — manual audits available now.

---

## What Fynor checks

### MCP Servers
| Check | What it catches |
|-------|----------------|
| Response time (P95) | Latency regressions under agent-speed load |
| Error rate (24h rolling) | Silent failure patterns |
| Schema validation | MCP spec compliance drift |
| Retry behavior | Crash-on-transient-failure bugs |
| Auth token handling | Credential exposure and rotation failures |
| Rate limit compliance | Runaway request patterns |
| Timeout handling | Hard hangs vs. graceful degradation |
| Log completeness | Missing audit trail |

### REST APIs (agent-specific)
| Check | What it catches |
|-------|----------------|
| Rate limit behavior at 1K req/min | Limits built for humans, not agents |
| Schema consistency across 1000 calls | Drift that breaks agent parsing |
| Token refresh under sustained load | Auth failures at call #10,001 |
| Cache header presence | 10x cost from uncached responses |
| Compression support | Bandwidth waste at agent call volume |
| Pagination completeness | Agents that silently miss records |

### GraphQL APIs
| Check | What it catches |
|-------|----------------|
| Query depth limits | Runaway agent queries |
| Introspection availability | Agent schema discovery |
| Error format consistency | Inconsistent error handling |
| Subscription stability | Dropped agent event streams |

### gRPC Services
| Check | What it catches |
|-------|----------------|
| Proto schema validation | Breaking changes without version bump |
| Streaming behavior | Bidirectional stream failures |
| Deadline propagation | Timeouts that cascade through agent pipelines |
| Connection pooling | Resource exhaustion under agent load |

### WebSocket Connections
| Check | What it catches |
|-------|----------------|
| Connection persistence | Drops under sustained agent sessions |
| Message ordering | Out-of-order events that corrupt agent state |
| Reconnection behavior | Silent failures after disconnect |
| Binary/text frame handling | Malformed frames that crash agent parsers |

### SOAP Services
| Check | What it catches |
|-------|----------------|
| WSDL schema validation | Spec drift |
| Fault format consistency | Unhandled error states in agents |
| Encoding compliance | UTF-8 and character encoding failures |

### CLIs (as agent tools)
| Check | What it catches |
|-------|----------------|
| Exit code consistency | CLIs that exit 0 on failure (breaks agent logic) |
| JSON output mode | CLIs that only output human-readable text |
| Non-interactive mode | CLIs that hang waiting for human input |
| Help text completeness | Undiscoverable commands for agent tool-use |
| Stderr vs stdout discipline | Mixed output that breaks agent parsing |

### Security (all interface types)
| Check | What it catches |
|-------|----------------|
| TLS enforcement | Unencrypted agent traffic |
| CORS configuration | Overly permissive cross-origin access |
| Injection handling | SQL, command, and prompt injection vectors |
| Credential scanning | Secrets leaked in response bodies or headers |
| Rate limit presence | No protection against agent-driven abuse |
| Input size limits | Unbounded inputs that crash services |

---

## ROI

| Dimension | What Fynor delivers |
|-----------|-------------------|
| Better solution | First agent-specific reliability standard — not adapted from human-use testing |
| Better data structure | Schema consistency validation across 1000+ calls catches drift before agents hit it |
| Data security | 6-layer security audit across every interface type |
| Cost reduction | Cache, compression, and rate limit checks reduce agent infrastructure cost by 40-70% |
| Better efficiency | Identifies the specific calls that slow agent pipelines |
| Better optimization | Pagination, batching, and connection reuse checks |
| Value for money | One $5K audit prevents one production incident that costs $50K-$500K |
| Profit increase | Agent-ready certification lets teams ship AI features 3x faster |
| Time saving | Audit cycle from 6 weeks to 3 days |
| Solving discomfort | CTOs know their infrastructure is agent-ready before agents hit it |

---

## Architecture

```
fynor/
├── checks/
│   ├── mcp/          # MCP server reliability
│   ├── rest/         # REST API agent-readiness
│   ├── graphql/      # GraphQL agent-readiness  
│   ├── grpc/         # gRPC agent-readiness
│   ├── websocket/    # WebSocket agent-readiness
│   ├── soap/         # SOAP agent-readiness
│   ├── cli_tool/          # CLI tool agent-readiness
│   └── security/     # Cross-cutting security audit
├── report/           # Audit report generation
└── ontology/         # Domain correctness rules (Phase C)
```

---

## Why this exists

Every category of software needs an agents-first rebuild. The APIs, MCPs, and CLIs
that AI agents use were designed for human consumption — predictable request rates,
readable errors, interactive workflows. Agents break all of these assumptions.

Fynor is the reliability layer for the agents-first transition.

---

## Built by

[Fynor Technologies](https://fynor.tech) — AI reliability auditing for agent-facing infrastructure.  
Building the ground truth standard for agent-ready software.

---

## Roadmap

- [ ] v0.1 — MCP checks CLI, 8 checks (November 2026)
- [ ] v0.2 — REST and security checks (December 2026)
- [ ] v0.3 — GraphQL and WebSocket checks (Q1 2027)
- [ ] v0.4 — gRPC and SOAP checks (Q1 2027)
- [ ] v0.5 — CLI tool checks (Q2 2027)
- [ ] v1.0 — Full platform, GitHub Action, hosted dashboard (Q2 2027)
- [ ] v2.0 — Domain ontology checks for FinTech and healthcare AI agents
