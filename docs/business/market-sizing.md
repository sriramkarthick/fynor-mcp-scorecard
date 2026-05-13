# Fynor — Market Sizing

**Last updated:** 2026-05-13

---

## Summary

| Market | Size | Fynor's Addressable Share |
|--------|------|--------------------------|
| TAM — All AI agent infrastructure tooling | $4.2B (2026) → $28B (2030) | Any AI-facing interface needs reliability measurement |
| SAM — API/MCP/interface operators deploying for agents | $680M (2026) | Directly served by Layer 1 checks |
| SOM — Reachable in 5 years via GTM motion | $34M | Conservative 5% SAM capture |

---

## Total Addressable Market (TAM)

**Definition:** Every company deploying or operating software that AI agents call.

**Data anchors (2026):**

- **97 million MCP server downloads/month** (Anthropic, April 2026) — the fastest-growing protocol in AI tooling history
- **30 million+ developers** worldwide (Stack Overflow Developer Survey, 2025)
- **AI agent deployment rate:** Estimated 18% of enterprise software teams deploying AI agents by end 2026 (Gartner, 2025 AI Adoption Report)
- **DevOps/observability market:** $12.9B in 2025, growing at 19% CAGR (MarketsandMarkets, 2025)

**TAM calculation:**

Layer 1 (Software for Agents) TAM:
- 30M developers × 18% AI agent deployment = 5.4M developers with AI agent workloads
- Willingness to pay for reliability tooling: estimated $80/developer/year (comparable to Postman Pro at $49/month vs. free)
- **Layer 1 TAM: 5.4M × $80 = $432M/year**

Layer 2 (AI OS) TAM:
- Fortune 2000 companies deploying regulated AI agents by 2028: estimated 800
- Average spend on AI compliance tooling: $150K/year (conservative, comparable to SOC2 audit costs)
- **Layer 2 TAM: 800 × $150K = $120M/year (2028 estimate)**

Layer 3 (Company Brain) TAM:
- Knowledge management software market: $20B (2025, IDC)
- AI-queryable knowledge layer addressable portion: ~15%
- **Layer 3 TAM: $3B/year**

**Combined TAM (2030):** ~$3.6B across all three layers — conservative estimate
excluding the broader AI infrastructure market expansion.

---

## Serviceable Addressable Market (SAM)

**Definition:** The subset of the TAM that Fynor can reach with its current
product and sales motion.

**Layer 1 SAM (2026–2028):**

MCP server operators and REST API providers who:
1. Know their API will be called by AI agents (already deploying)
2. Have a budget for developer tooling ($50–$999/month)
3. Are reachable via open source community, GitHub, Hacker News, and Product Hunt

Sizing:
- Estimated active MCP server deployments: 200,000+ (derived from 97M downloads ÷ ~500 average downloads per unique server)
- Estimated willingness to pay: 5% of MCP operators = 10,000 potential customers
- Average revenue per customer: $68/month (mix of Pro and Team)
- **Layer 1 SAM: 10,000 × $68 × 12 = $8.2M/year**

REST API operators (v0.2+, Month 9):
- Estimated 2M+ public REST APIs (ProgrammableWeb, 2025)
- AI-facing APIs (those expecting agent traffic): estimated 8% = 160,000
- Willingness to pay: 3% of AI-facing API operators = 4,800 customers
- Average $68/month
- **REST SAM add: 4,800 × $68 × 12 = $3.9M/year**

**Layer 1 total SAM: ~$12M/year (2027)**

**Layer 2 SAM (2028+):**
- Regulated enterprises deploying AI agents: FinTech (FINRA), healthcare (FDA 21 CFR Part 11), legal
- Estimated 400 enterprises willing to pay for AI OS monitoring in Year 3 of availability
- Average contract: $7,500/month
- **Layer 2 SAM: 400 × $7,500 × 12 = $36M/year (2029)**

**Combined SAM by 2029: ~$48M/year**

---

## Serviceable Obtainable Market (SOM)

**Definition:** The realistic revenue Fynor can capture in 5 years (by 2031).

Conservative capture rates:
- Layer 1: 5% of Layer 1 SAM = $600K/year by 2028, growing to $2.4M by 2031
- Layer 2: 8% of Layer 2 SAM = $1.2M by 2029, growing to $3.2M by 2031
- Layer 3: Minimal in 5-year window (Phase D begins 2030)

**5-year SOM (2031): ~$6M ARR** — conservative floor.

**Why conservative:** The SOM assumes no viral growth from Agent-Ready badge
adoption, no partnership channel, and no inbound from regulated-industry mandates
(EU AI Act enforcement begins 2027 and will drive compliance tool spending).

**Upside scenario (badge virality):** If the Agent-Ready badge achieves even 10%
of the adoption rate of shields.io badges (used by 2M+ GitHub repos), MCP server
operators adopt it as a community standard. This could 5-10× the Layer 1 capture rate.
Not modeled in base case.

---

## Market Timing

**Why now is the right moment:**

| Factor | Evidence |
|--------|---------|
| MCP protocol traction | 97M downloads/month, April 2026 — fastest-growing AI protocol |
| No direct competitor | Nothing measures AI agent reliability. The gap is confirmed. |
| Regulatory tailwinds | EU AI Act (enforcement 2027), US AI Executive Order (2025), FINRA guidance on AI in trading |
| AI agent deployment wave | Gartner: 25% of enterprise customer interactions will use AI agents by 2027 |
| Developer tooling investment | Postman ($1B valuation), Datadog ($18B) — developer reliability tools command premium multiples |

**The window:** MCP server operators are building now without reliability tooling.
The first tool to establish the Agent-Ready certification standard sets the benchmark
that all others are measured against. First-mover advantage in standard-setting is
defensible (similar to how Stripe defined payment API standards).

---

## References

- Gartner (2025). AI Adoption in Enterprise Software Development.
- MarketsandMarkets (2025). DevOps Market Size and Forecast.
- IDC (2025). Knowledge Management Software Market Share.
- Anthropic (2026). MCP Protocol Usage Statistics, April 2026.
- Stack Overflow (2025). Developer Survey 2025.
