# Fynor — Risk Register

**Last updated:** 2026-05-13  
**Review cadence:** Quarterly  
**Owner:** Sriram Karthick

---

## Risk Matrix Key

| Likelihood | Impact | Rating |
|-----------|--------|--------|
| High × High | Critical | Immediate mitigation required |
| High × Medium | High | Mitigation plan within 30 days |
| Medium × High | High | Mitigation plan within 30 days |
| Medium × Medium | Medium | Monitor quarterly |
| Low × Any | Low | Accept or monitor |

---

## Technical Risks

### T1 — Check Results Are Not Reproducible (High × High = Critical)

**Description:** The same target server produces different scores on consecutive
runs due to transient server behavior, network variance, or non-determinism in
the check algorithms.

**Impact:** Destroys the core value proposition. If developers cannot trust that
a B score today means B tomorrow, the certification system is worthless.

**Mitigation:**
- All 8 checks are deterministic algorithms (ADR-01 governing rule)
- P95 over 20 requests smooths single-request variance
- Run-to-run score variance documented and communicated to users
- "Score band" (±5 points) disclosed as normal variance in documentation

**Status:** Accepted — variance is inherent in probabilistic workloads. Managed
through documentation and the 30-consecutive-days certification threshold.

---

### T2 — MCP Protocol Changes Break the Schema Check (Medium × High = High)

**Description:** The MCP specification evolves. A schema check written for
JSON-RPC 2.0 v1 may produce false failures against MCP v2.

**Impact:** False negatives (real failures missed) or false positives (passing
servers graded as failing).

**Mitigation:**
- Schema check validates the JSON-RPC 2.0 envelope (stable standard, not MCP-specific)
- MCP-specific validation is separated from the JSON-RPC validation
- Fynor tracks MCP specification releases (Anthropic GitHub)
- Schema check versioned: `check_schema_v1`, `check_schema_v2` as protocol evolves

**Status:** Active — monitor MCP spec release cadence.

---

### T3 — Target Server Blocks Fynor's IP Range (Medium × Medium = Medium)

**Description:** The burst test traffic (50 requests at 20 req/s) looks like a
DDoS from the server's perspective. The server blocks Fynor's IP range.

For Phase A (Railway), this is exacerbated: Railway uses shared egress IPs across
all tenants. Stripe, GitHub, OpenAI, and other major APIs already block Railway's
IP range, making checks against those targets inaccurate regardless of check design.

**Impact:** Check run fails with connection errors, producing inaccurate results.
Damages relationship with target server operator.

**Mitigation:**
- Fynor's static IP range documented and published — operators can whitelist
- Rate limit check fires only 50 requests (well below DoS thresholds)
- User-Agent header identifies Fynor explicitly: `Fynor-Reliability-Checker/1.0`
- Terms of Service require users to have permission to run checks against targets
  they do not own
- **Phase A Railway limitation disclosed in UI (Decision D11 — 2026-05-15):**
  Results page shows: "Checks against Stripe, GitHub, OpenAI may be less accurate —
  their APIs block Railway's shared egress IPs. Use the CLI tool for accurate results."
- **Phase B fix:** ECS Fargate tasks use Fynor-owned static NAT Gateway IPs.
  Operators can whitelist this range once it's published.

**Status:** Active — Phase A limitation documented in UI. Phase B requires static IP publication.

---

### T5 — Rate Limiter Bypass via DynamoDB Overload (High × High = Critical) [NEW]

**Description:** The original design used DynamoDB as the sole rate limiter.
An attacker who floods DynamoDB (or causes DynamoDB to become unavailable) would
disable rate limiting entirely ("fail open"). This allows unlimited POST /check
requests, each of which makes outbound HTTP requests from Fynor's infrastructure.

**Impact:** Fynor's infrastructure is weaponised as a DDoS amplifier. Each check
request can trigger up to 8 outbound calls to the target. Cost also scales unboundedly.

**Mitigation (Decision D4 — 2026-05-15):**
- **Primary:** Cloudflare rate limiting — 100 req/30s per IP, runs BEFORE Railway,
  independent of DynamoDB availability. Config: `infra/cloudflare/`.
- **Secondary:** DynamoDB rate limit table (PK=ratelimit#{ip_hash}, TTL=now+30s).
  Catches edge cases not blocked by Cloudflare (e.g. Cloudflare PoP counting).
- The two layers are independent. DynamoDB down → Cloudflare still blocks.
  Cloudflare misconfigured → DynamoDB catches the overflow.

**Status:** Mitigated — Cloudflare primary layer implemented in `infra/cloudflare/`.

---

### T4 — Claude API Latency Affects Junction 1 (Month 7) (Low × Medium = Low)

**Description:** The Failure Interpretation Agent (Junction 1) calls the Claude API.
High latency or outages in the Claude API delay remediation recommendations.

**Impact:** Interpretations queue up. Developers experience delayed recommendations.

**Mitigation:**
- Junction 1 is asynchronous — check results are delivered immediately, interpretations
  are delivered when ready (email/webhook notification)
- Fallback: if Claude API is unavailable, interpretation is marked "pending" and
  retried within 24 hours
- Human review gate means interpretations are never on the critical path for check delivery

**Status:** Low priority — acceptable given async delivery model.

---

## Business Risks

### B1 — Datadog Launches Agent Reliability Checks (High × High = Critical)

**Description:** Datadog (market cap ~$18B, 2025) adds agent-specific reliability
checks to their existing observability platform. Their distribution advantage makes
them the default for enterprise buyers.

**Impact:** Compresses Fynor's Enterprise TAM significantly. May cap growth at
Team tier.

**Mitigation:**
- **Accelerate Phase C:** Ground truth database moat is not replicable by Datadog
  without years of live deployments. Get to Phase C before Datadog enters.
- **Regulatory positioning:** Establish FINRA/FDA compliance relationships before
  Datadog can claim them
- **OSS lock-in:** Open source check engine makes Fynor the community standard —
  Datadog would be a proprietary alternative to the open standard

**Timeline trigger:** If Datadog announces agent reliability features, accelerate
Phase C timeline by 6 months.

**Status:** Monitoring — track Datadog product roadmap quarterly.

---

### B2 — MCP Protocol Fails to Reach Critical Adoption (Medium × High = High)

**Description:** MCP (97M downloads/month, April 2026) fails to become the dominant
AI agent communication protocol. An alternative (OpenAI's function calling, Google's
AGI protocol) displaces it.

**Impact:** Layer 1 v0.1 is MCP-only. If MCP stagnates, the initial market is smaller.

**Mitigation:**
- Fynor's architecture is interface-agnostic (BaseAdapter pattern)
- REST API support ships Month 9 (v0.2) — independent of MCP adoption
- The 8 checks apply to any interface type
- "MCP-first" is a GTM strategy, not an architectural constraint

**Status:** Active — monitor MCP adoption metrics monthly.

---

### B3 — Enterprise Sales Cycle Too Long for Cash Flow (Medium × Medium = Medium)

**Description:** Enterprise contracts ($999/month+) require procurement approval,
security reviews, and legal sign-off. Sales cycles of 6-12 months may strain
pre-funding cash flow.

**Impact:** ARR growth lags model projections. Seed round required earlier than planned.

**Mitigation:**
- Pro/Team tier ($49/$249) provides early cash flow without enterprise sales cycles
- Manual audit contracts (Calendly funnel) provide $500–$2,000 per engagement upfront
- Enterprise pipeline started at Month 18 (not Month 6) to align with seed funding

**Status:** Accepted — managed through tier diversification.

---

### B4 — AI Act / Regulatory Compliance Changes Scope (Low × High = Medium)

**Description:** EU AI Act (enforcement 2027) or US AI Executive Order imposes
unexpected compliance requirements on AI reliability tools themselves (not just
on the AI systems they measure).

**Impact:** Compliance cost increases. Potential liability exposure if a
certified server causes harm.

**Mitigation:**
- Engage legal counsel before Enterprise launch (Month 24 target)
- Terms of Service: Fynor certification is an opinion, not a warranty
- Limit liability clause: Fynor's liability capped at 3 months of subscription fees
- SOC 2 Type II audit (Month 24) demonstrates Fynor's own operational compliance

**Status:** Active — legal review required before Enterprise launch.

---

## Market Risks

### M1 — LLM Providers Build Native Interface Reliability Into Their Protocols (Medium × Medium = Medium)

**Description:** Anthropic, OpenAI, or Google build reliability guarantees directly
into the MCP/function-calling protocol, eliminating the need for an external
reliability checker.

**Impact:** Reduces Layer 1 TAM for hosted MCP servers.

**Mitigation:**
- Protocol-level reliability handles the transport layer, not the application layer
- Fynor checks application-level behavior: does the server return the right schema?
  Does it enforce auth? Does it rate-limit correctly? These are not transport concerns.
- Phase C (AI OS) is not addressable by protocol improvements

**Status:** Low priority — protocol-level and application-level reliability are
fundamentally different concerns.

---

## Risk Summary

| ID | Risk | Rating | Status |
|----|------|--------|--------|
| T1 | Check reproducibility | Critical | Managed |
| T2 | MCP protocol changes | High | Active |
| T3 | IP blocking | Medium | Active |
| T4 | Claude API latency | Low | Accepted |
| B1 | Datadog enters | Critical | Monitoring |
| B2 | MCP protocol fails | High | Active |
| B3 | Enterprise sales cycle | Medium | Accepted |
| B4 | AI regulatory compliance | Medium | Active |
| M1 | Protocol-native reliability | Medium | Low priority |
