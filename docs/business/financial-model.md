# Fynor — Financial Model

**Confidential. Internal use only.**  
**Last updated:** 2026-05-13  
**Target exit:** $80M+ acquisition, 2033–2036

---

## Pricing Architecture

Four tiers designed to match the three-layer product roadmap. Free drives adoption.
Each paid tier corresponds to a specific buyer persona.

| Tier | Price | Target Persona | Core Value |
|------|-------|----------------|------------|
| **Free** | $0 | Individual developer, open source maintainer | CLI + 8 checks + local history |
| **Pro** | $49/month | MCP server operator, solo AI developer | Hosted dashboard + 5 targets + 30-day history + Agent-Ready badge |
| **Team** | $249/month | Engineering team at AI-first startup | 25 targets + CI/CD integration + Slack alerts + 90-day history |
| **Enterprise** | $999/month | Regulated-industry AI deployer | Unlimited targets + compliance reports + custom ontology + dedicated support + 1-year history |

### Phase C Add-on: AI OS Monitoring (2027+)

| Tier | Price | What It Covers |
|------|-------|----------------|
| **AI OS Starter** | $2,500/month | 1 domain, 1 agent, 500 decisions/month logged + flagged |
| **AI OS Business** | $7,500/month | 3 domains, 10 agents, 5,000 decisions/month, quarterly compliance report |
| **AI OS Enterprise** | Custom ($15K–$50K/month) | Unlimited agents, regulator-facing audit trail, dedicated domain expert review |

### Phase D: Company Brain (2030+)

| Tier | Price | What It Covers |
|------|-------|----------------|
| **Brain Standard** | $5,000/month | Hosted .ontology.json, versioned, queryable by agents |
| **Brain Enterprise** | $20,000/month | Custom domain ontology, ground truth labeling service, annual review |

---

## ARR Projections — 7-Year Model

Key assumptions:
- Free-to-Pro conversion: 3% of active CLI installs
- Pro-to-Team upgrade: 12% of Pro accounts (team adoption)
- Team-to-Enterprise upgrade: 8% of Team accounts
- Monthly churn: Pro 4%, Team 2.5%, Enterprise 1%
- Phase C adoption: 15% of Enterprise clients add AI OS monitoring
- Phase D adoption: 30% of AI OS Business/Enterprise clients add Company Brain

### Year-by-Year Summary

| Year | Month Range | Pro | Team | Enterprise | AI OS | Brain | MRR | ARR |
|------|-------------|-----|------|------------|-------|-------|-----|-----|
| Y1 | M6–M18 | 150 | 15 | 0 | 0 | 0 | $11,085 | $133K |
| Y2 | M18–M30 | 450 | 60 | 5 | 0 | 0 | $37,545 | $451K |
| Y3 | M30–M42 | 900 | 160 | 20 | 0 | 0 | $83,780 | $1.0M |
| Y4 | M42–M54 | 1,600 | 320 | 55 | 5 | 0 | $187,300 | $2.2M |
| Y5 | M54–M66 | 2,400 | 500 | 100 | 20 | 0 | $330,000 | $3.96M |
| Y6 | M66–M78 | 3,200 | 700 | 160 | 50 | 5 | $539,800 | $6.5M |
| Y7 | M78–M90 | 4,000 | 900 | 220 | 80 | 15 | $766,000 | $9.2M+ |

**Exit target range:** $15M–$20M ARR by Year 8–9 → 4–6× ARR multiple = **$60M–$120M**

---

## Detailed Year 1–3 Build (Pre-Phase C)

### Year 1 (Month 6–18): Open Source + First Revenue

**Go-to-market:** Developer adoption via MCP community (97M downloads/month, 2026).
Outreach to MCP server maintainers via GitHub, Hacker News, Dev.to.
First 5 paying clients from Upwork/Toptal audit contracts ($500–$2,000/engagement).

| Quarter | Pro | Team | MRR |
|---------|-----|------|-----|
| Q1 (M6–M9) | 20 | 0 | $980 |
| Q2 (M9–M12) | 60 | 4 | $3,936 |
| Q3 (M12–M15) | 110 | 10 | $7,880 |
| Q4 (M15–M18) | 150 | 15 | $11,085 |

**Year 1 total revenue:** ~$55K (ramp from $0)

### Year 2 (Month 18–30): REST API + GitHub Action

v0.2 ships (Month 9) — REST adapter opens 10× larger market than MCP alone.
GitHub Action (Month 8) creates organic discovery via CI/CD runs.

| Quarter | Pro | Team | Enterprise | MRR |
|---------|-----|------|------------|-----|
| Q5 | 200 | 22 | 1 | $15,277 |
| Q6 | 280 | 35 | 2 | $23,055 |
| Q7 | 370 | 48 | 4 | $31,277 |
| Q8 | 450 | 60 | 5 | $37,545 |

**Year 2 total revenue:** ~$265K

### Year 3 (Month 30–42): All Interface Types + Certification

v1.0 ships (Month 20) with all 7 interface types + hosted certification.
Agent-Ready badge becomes a developer-community signal (similar to Shields.io badges).

| Quarter | Pro | Team | Enterprise | MRR |
|---------|-----|------|------------|-----|
| Q9 | 550 | 80 | 8 | $51,688 |
| Q10 | 680 | 105 | 12 | $65,520 |
| Q11 | 800 | 135 | 16 | $79,525 |
| Q12 | 900 | 160 | 20 | $83,780 |

**Year 3 total revenue:** ~$750K. **Cumulative Year 1–3:** ~$1.07M

---

## Unit Economics

| Metric | Value | Notes |
|--------|-------|-------|
| **Gross Margin** | ~82% | SaaS infrastructure costs are primarily compute for burst-test loads |
| **CAC (Pro)** | ~$40 | Primarily content marketing + open source community |
| **CAC (Team)** | ~$200 | SDR-assisted, GitHub outreach |
| **CAC (Enterprise)** | ~$2,500 | Sales-assisted, Calendly audit funnel |
| **LTV (Pro, 25-month avg)** | ~$1,225 | At 4% monthly churn, avg lifetime = 25 months |
| **LTV (Team, 40-month avg)** | ~$9,960 | At 2.5% monthly churn |
| **LTV (Enterprise, 100-month avg)** | ~$99,900 | At 1% monthly churn |
| **LTV/CAC (Pro)** | 30× | Excellent for PLG motion |
| **LTV/CAC (Enterprise)** | 40× | Strong for sales-assisted |

---

## Infrastructure Costs

Estimated monthly infrastructure cost at various ARR levels:

| ARR Level | Monthly Infra Cost | Gross Margin |
|-----------|-------------------|--------------|
| $133K (Y1) | ~$2,000 | 82% |
| $1M (Y3) | ~$8,000 | 84% |
| $4M (Y5) | ~$25,000 | 84% |
| $10M (Y8) | ~$60,000 | 85% |

Primary cost drivers:
- **Compute:** Burst HTTP testing requires ephemeral load-generation workers. At $10/1,000 runs and 5 runs/target/week for 1,000 targets = $50/week = $200/month at Team scale
- **Storage:** JSONL history + ground truth DB grows linearly with client count. At $0.02/GB/month, even 1TB = $20/month
- **Bandwidth:** Check traffic is small (JSON payloads, <1KB per request)

---

## Exit Thesis

### Target: $80M+ acquisition, 2033–2036

**Exit trigger:** Phase C (AI OS) is live with 50+ enterprise clients. Ground truth
database has 5,000+ labeled domain-expert decisions. Phase D (Company Brain) has
shipped with first commercial customers.

**Valuation math:**

| Year | ARR | Multiple | Valuation |
|------|-----|----------|-----------|
| Y7 (2033) | $9.2M | 8× | $73.6M |
| Y8 (2034) | $13M | 7× | $91M |
| Y9 (2035) | $18M | 5× | $90M |

The 5–8× ARR multiple is justified by:
1. **Proprietary ground truth database** (no competitor can replicate without years of live deployments)
2. **Regulatory tailwinds** (FINRA, FDA, EU AI Act all require agent decision auditability)
3. **Network effects** (more domain ontology rules → more clients → more ground truth records → better rules)
4. **Comparable acquisitions:**
   - PagerDuty acquired by Thoma Bravo (2023) at ~6× ARR
   - Datadog IPO implied 20× ARR (different scale)
   - LogicMonitor acquired at ~5× ARR

### Likely Acquirers

| Acquirer | Strategic Fit | Bid Rationale |
|----------|--------------|---------------|
| Datadog | Add AI agent monitoring to observability platform | Ground truth DB + agent reliability = new product line |
| PagerDuty | Extend incident management to AI agent failures | Agent-Ready certification = new revenue stream |
| Anthropic / OpenAI | Own the reliability layer for their own MCP ecosystem | Defensive acquisition, platform lock-in |
| ServiceNow | AI governance + compliance reporting = direct product fit | Phase C (AI OS) maps to their workflow automation market |
| Cisco (AppDynamics) | AI observability = natural extension | Performance + security checks align with AppD roadmap |

---

## Funding Strategy

**Phase B (now–Month 20):** Bootstrapped. Revenue from:
- Open source community (free)
- Manual audit contracts via Calendly ($500–$2,000 each)
- First 50 Pro subscribers

**Seed round (Month 18–24):** $500K–$1.5M at ~$5M pre-money valuation.
Use: hire one engineer, fund Phase C development, one US sales rep.

**Series A (Month 30–42):** $3M–$5M at ~$15M pre-money.
Use: full Phase C build, 3 more engineers, India + US marketing.

**Series B or exit (Month 54–66):** At $4M+ ARR — either raise growth capital
or receive acquisition offer. Strong preference for acquisition over IPO at this scale.
