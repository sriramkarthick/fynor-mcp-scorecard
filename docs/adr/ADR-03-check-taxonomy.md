# ADR-03: Check Taxonomy — Why Exactly These Eight Checks

**Status:** Accepted  
**Date:** 2026-05-13  
**Deciders:** Sriram Karthick (Fynor Technologies)

---

## Context

Fynor v0.1 implements exactly eight checks for MCP servers. The selection must be:

1. **Complete** — covers every agent-specific failure mode that differs from human-facing failures
2. **Non-redundant** — each check catches something the others cannot
3. **Grounded** — each check must be traceable to published reliability engineering literature
4. **Deterministic** — each check must produce the same result on the same server state

This ADR documents the taxonomy that justifies the specific eight checks and
explicitly excludes alternatives that were considered and rejected.

---

## Theoretical Foundation

The eight checks are derived from three intersecting frameworks:

### 1. Google SRE Four Golden Signals (Beyer et al., 2016)

The four golden signals for service health monitoring:
- **Latency** → `latency_p95`
- **Traffic** → `rate_limit` (rate limiting is the traffic-handling contract)
- **Errors** → `error_rate`
- **Saturation** → `timeout` (hard hangs are the saturated-server signal)

These four signals are the industry standard for any service monitoring.
The agent-specific context requires that all four are tested at machine-speed
load, not single-request probing.

### 2. Byzantine Fault Tolerance — Correctness Under Adversarial Input (Lamport et al., 1982)

AI agents send inputs that humans would never send — malformed JSON, unexpected
parameter types, extreme values. A server that handles human input correctly may
fail silently on machine-generated input. Two checks address this:
- `schema` — does the server emit correctly structured responses?
- `retry` — does the server handle malformed input gracefully?

These are the "correctness under non-human input" checks.

### 3. NIST SP 800-160 Security Engineering (Ross et al., 2016)

Security in the agent context has a specific failure mode: AI agents may log,
cache, or forward response headers. A credential leak that a human would notice
and discard is captured and propagated by an agent. Two checks address this:
- `auth_token` — credential exposure and authentication enforcement
- `log_completeness` — structured audit trail (required for regulated environments)

---

## The Eight Checks — Formal Classification

| # | Check | Signal Class | Agent-Specific Failure Mode | Rejected Alternative |
|---|-------|-------------|----------------------------|----------------------|
| 1 | `latency_p95` | Latency | P95 regression under burst load — agents do not back off like humans | P50 (median hides tail; agents hit tails at scale) |
| 2 | `error_rate` | Errors | Silent failure accumulation over 50-request window | Single-request error check (misses probabilistic failures) |
| 3 | `schema` | Correctness | JSON-RPC 2.0 envelope violations — agents cannot recover from structural errors | Field-level validation (too MCP-version-specific) |
| 4 | `retry` | Correctness | Server crash on malformed input — kills entire agent pipeline | Only testing valid inputs (misses agent-generated edge cases) |
| 5 | `auth_token` | Security | Credential leakage via headers/URL; missing 401 on unauthenticated calls | Manual credential audit (not reproducible) |
| 6 | `rate_limit` | Traffic | Missing 429 + Retry-After — agent floods endpoint without backoff signal | Connection-level throttling (not visible to agents) |
| 7 | `timeout` | Saturation | Hard hang with no response — blocks entire pipeline thread | Soft latency warning (timeout and high latency are distinct failure modes) |
| 8 | `log_completeness` | Auditability | No structured audit trail — required for regulated AI deployments | Application-level logging (out of scope for interface check) |

---

## Why P95, Not P50 or P99

`latency_p95` was chosen deliberately over P50 (median) and P99 (99th percentile).

**P50 rejected:** The median hides tail behavior. An agent running 1,000 calls/hour
hits the 95th percentile approximately 50 times. P50 tells you nothing about
those 50 calls. A server with P50=100ms and P95=5,000ms will not cause issues
for a human user who refreshes occasionally. It will destroy an agent pipeline.

**P99 rejected:** P99 over 20 requests is statistically unstable. With only 20
observations, the 99th percentile is determined by a single data point. This
makes it highly sensitive to transient spikes and produces inconsistent grades
across runs on the same server.

**P95 over 20 requests** gives the 19th-highest latency — stable enough to be
reproducible, sensitive enough to catch tail behavior that matters at agent scale.

---

## Why 50 Requests for Error Rate

The `error_rate` check fires 50 requests at 1 req/s. This was chosen to:
- Detect probabilistic failures that occur in 5-20% of requests (requires N≥20 minimum)
- Stay within typical free-tier rate limits (50 req/min is below most API quotas)
- Complete in under 60 seconds (fits comfortably in a CI/CD pipeline timeout)

The 5% pass threshold was derived from the SRE error budget model (Beyer et al., 2016):
a service with 99.5% availability has a 0.5% error rate. A 5% error rate implies
~99.95% of agents calling a 5%-error-rate server will experience at least one failure
in a 100-call pipeline. At 8.2% (README example), a 50-step pipeline has a 98.5%
chance of hitting at least one error — effectively guaranteed failure.

---

## Checks Considered and Explicitly Rejected

| Rejected Check | Reason for Rejection |
|----------------|----------------------|
| `dns_resolution` | Infrastructure check, not an interface reliability check. Tests the network, not the server. |
| `ssl_certificate` | Covered by standard TLS validation in httpx. Not an agent-specific failure mode. |
| `response_size` | Useful for humans (page load). AI agents handle large payloads natively. Not a reliability signal. |
| `cors_headers` | Browser-only concern. AI agents do not use CORS. |
| `openapi_completeness` | Useful for REST APIs (v0.2). Not applicable to MCP JSON-RPC. |
| `websocket_upgrade` | v0.3 check. MCP v0.1 uses HTTP POST only. |
| `cache_headers` | Not an agent-specific failure mode. Caching behavior is a performance optimisation, not a reliability signal. |

---

## Extensibility Contract

The eight checks in v0.1 are for MCP servers only. Each interface type (REST, GraphQL,
gRPC, WebSocket, SOAP, CLI) will have its own eight checks, derived from the same
three frameworks (SRE golden signals, Byzantine fault tolerance, NIST security).

The taxonomy ensures that:
1. Every interface has checks in all three signal classes
2. Security checks always carry the ADR-02 cap rule
3. New checks are added at the category level, not arbitrarily

A new check requires a new entry in this ADR documenting which signal class it
belongs to, which agent-specific failure mode it detects, and which alternatives
were considered and rejected.

---

---

## Amendment 1 — Three New Checks (v0.2)

**Date:** 2026-05-14  
**Status:** Accepted

Three new checks are added to the MCP check set, expanding from 8 to 11 checks.
All three belong to the Reliability category (ADR-02, 40% weight).
The Security and Performance category compositions are unchanged.

### Check #9: `data_freshness`

| Field | Value |
|-------|-------|
| Signal class | Reliability — data currency |
| Agent-specific failure mode | Agent reasons over stale data, makes decisions based on outdated state. A human notices stale timestamps; an agent does not. |
| Pass threshold | score ≥ 60 (data age ≤ 24 hours) |
| Scoring | ≤5min→100, ≤60min→80, ≤24h→60 (pass), >24h→20, no timestamp→0 |
| Rejected alternatives | Response latency check (already `latency_p95`); content correctness (not deterministically verifiable) |

### Check #10: `tool_description_quality`

| Field | Value |
|-------|-------|
| Signal class | Reliability — tool discoverability |
| Agent-specific failure mode | Agent selects wrong tool due to absent or ambiguous tool description, causing incorrect or incomplete operations. Humans read documentation; agents rely entirely on tool descriptions at call time. |
| Pass threshold | score ≥ 60 (all tools have name + description ≥10 chars) |
| Scoring | Worst-case across all tools: full (desc≥50+schema)→100, adequate (desc≥20+schema)→80, minimal (desc≥10)→60 (pass), inadequate→20, no tools or no name→0 |
| Rejected alternatives | Semantic description quality assessment (requires AI judgment, non-deterministic) |

### Check #11: `response_determinism`

| Field | Value |
|-------|-------|
| Signal class | Reliability — structural consistency |
| Agent-specific failure mode | Agent parses response schema from call 1, fails on call 2 due to different keys or types, corrupts the context window with inconsistent data structures. |
| Pass threshold | score ≥ 60 (at least 2 of 3 probes structurally identical) |
| Scoring | All 3 identical→100, 2 of 3 identical→60 (pass), all different→0, any error→0 |
| Rejected alternatives | Full response equality check (data legitimately changes between calls); single-probe check (one probe cannot detect non-determinism) |

### Amendment to Check #5: `auth_token` — F4 Addition

A fourth failure condition is added to the existing `auth_token` check:

**F4: Invalid token signature accepted** — the server returns HTTP 200 when presented with a syntactically plausible but semantically invalid Bearer token. This detects servers that check token _presence_ but not token _validity_ (signature verification). F4 only fires if F2 did NOT fire (if F2 fires, the server accepts ALL requests regardless of auth, making F4 redundant).

Scoring model updated: 0 failures→100, 1→40, 2→10, 3→0, 4→0 (four failures is already the maximum and maps to 0 via the fallback).

The security cap rule is unchanged: any auth_token score of 0 still caps the overall grade at D.

### Updated Check Classification Table

| # | Check | Signal Class | Pass Threshold |
|---|-------|-------------|----------------|
| 1 | `latency_p95` | Performance — latency tail | score ≥ 60 |
| 2 | `error_rate` | Reliability — error budget | score ≥ 60 |
| 3 | `schema` | Reliability — protocol conformance | score ≥ 60 |
| 4 | `retry` | Reliability — recovery behavior | score ≥ 60 |
| 5 | `auth_token` | **Security** — credential handling (F1–F4) | score = 100 |
| 6 | `rate_limit` | Performance — resource exhaustion protection | score ≥ 60 |
| 7 | `timeout` | Reliability — hanging connection | score ≥ 60 |
| 8 | `log_completeness` | Reliability — observability | score ≥ 60 |
| 9 | `data_freshness` | Reliability — data currency | score ≥ 60 |
| 10 | `tool_description_quality` | Reliability — tool discoverability | score ≥ 60 |
| 11 | `response_determinism` | Reliability — structural consistency | score ≥ 60 |

---

## References

- Beyer, B. et al. (2016). *Site Reliability Engineering*. O'Reilly. Chapter 6.
- Lamport, L., Shostak, R., & Pease, M. (1982). The Byzantine Generals Problem. *ACM TPLS*.
- Ross, R. et al. (2016). *Systems Security Engineering*. NIST SP 800-160.
- Humble, J. & Farley, D. (2010). *Continuous Delivery*. Addison-Wesley. Chapter 8 (testing non-functional requirements).
- Nygard, M. (2007). *Release It!*. Pragmatic Programmers. Chapter 5 (stability patterns — timeout, circuit breaker).
