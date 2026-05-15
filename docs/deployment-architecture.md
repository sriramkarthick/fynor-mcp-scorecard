# Fynor — Deployment Architecture

**Last updated:** 2026-05-15  
**Version:** v1.1 — added Cloudflare rate limiting layer (Phase A) and Railway deployment (D4)

---

## Overview

Fynor has two deployment modes:

1. **CLI (open source):** Runs entirely on the developer's machine. No server required.
   Check history stored locally in `~/.fynor/history.jsonl`.

2. **Hosted (fynor.tech):** Managed service. Checks run from Fynor's infrastructure.
   History stored in Fynor's database. Badge and certification endpoints served globally.

This document describes the hosted architecture.

### Phase A vs Phase B

| | Phase A (Month 4–5) | Phase B (Month 6+) |
|---|---|---|
| **Compute** | Railway (PaaS) | AWS ECS Fargate |
| **Rate limiting** | Cloudflare (primary) + DynamoDB (secondary) | AWS API Gateway + Cloudflare |
| **Database** | DynamoDB on-demand | DynamoDB on-demand |
| **Config** | `infra/railway/railway.toml` + Cloudflare dashboard | Terraform (`infra/`) |

Phase A (Railway) is explicitly a stepping stone for the demand probe — not the
long-term architecture. The Cloudflare layer persists into Phase B.

---

## Architecture Diagram

### Phase A — Railway + Cloudflare (Month 4–5)

```
Developer / CI / GitHub Action
         │
         │  HTTPS POST /api/v1/check
         ▼
┌─────────────────────────────────────────────────────┐
│              Cloudflare (Layer 0 — PRIMARY)         │
│   Rate limiting: 100 req/30s per IP                │
│   WAF: block empty User-Agent on POST /check        │
│   DNS proxy: api.fynor.tech → Railway CNAME         │
│                                                     │
│   Decision D4: Cloudflare runs BEFORE Railway.      │
│   If DynamoDB is down, Cloudflare still blocks.     │
│   Config: infra/cloudflare/  SETUP: infra/cloudflare/SETUP.md  │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│              Railway (Phase A compute)              │
│   FastAPI app · uvicorn · 2 workers                 │
│   Auto-sleep on idle (warm-up probe mitigates this) │
│   Config: infra/railway/railway.toml                │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│   DynamoDB (SECONDARY rate limit + result storage)  │
│   PK=ratelimit#{ip_hash}, TTL=now+30s               │
│   Fallback if Cloudflare misconfigured; NOT primary │
└─────────────────────────────────────────────────────┘
```

### Phase B — AWS (Month 6+, full production)

```
Developer / CI / GitHub Action
         │
         │  HTTPS POST /api/v1/check
         ▼
┌─────────────────────────────────────────────────────┐
│              Cloudflare (Layer 0 — persists)        │
│   Rate limiting · WAF · DDoS protection             │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                  API Gateway (AWS API Gateway)       │
│   Rate limiting · Auth · Request validation         │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│              Check Orchestrator (Lambda / ECS)      │
│   Resolves adapter type · Dispatches 8 check tasks  │
└──────┬──────────────────┬──────────────────────┬────┘
       │                  │                      │
       ▼                  ▼                      ▼
┌──────────────┐  ┌──────────────┐  ┌────────────────────┐
│  Check Workers (ECS Fargate — ephemeral, burst-capable) │
│  latency_p95 │  │  auth_token  │  │  rate_limit  │ ...  │
│  error_rate  │  │  schema      │  │  timeout     │      │
└──────┬───────┘  └──────┬───────┘  └──────┬─────────────┘
       │                  │                 │
       └──────────────────┼─────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│              Scorer + History Writer                │
│   ADR-02 weighted scoring · history.jsonl append    │
└──────────────────────┬──────────────────────────────┘
                       │
           ┌───────────┴────────────┐
           │                        │
           ▼                        ▼
┌─────────────────────┐   ┌────────────────────────────┐
│  DynamoDB           │   │  S3 (JSONL history archive) │
│  Target metadata    │   │  Immutable, partitioned by  │
│  Check results      │   │  target + year/month        │
│  Cert status        │   └────────────────────────────┘
└─────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────┐
│             Pattern Detector (Lambda, nightly)      │
│   Reads 30-day history window per target            │
│   Writes patterns.jsonl + alerts.jsonl              │
└─────────────────────────────────────────────────────┘
           │
           ▼ (Month 7 — AI Junction 1)
┌─────────────────────────────────────────────────────┐
│         Failure Interpreter (Lambda + Claude API)   │
│   Called when PatternDetector flags anomaly         │
│   Result → review queue (human approval required)  │
└─────────────────────────────────────────────────────┘

Badge + Cert Endpoints (separate service — high availability):
┌─────────────────────────────────────────────────────┐
│  https://fynor.tech/badge/{cert-id}  (SVG badge)   │
│  https://fynor.tech/cert/{cert-id}   (JSON cert)   │
│  Served from CloudFront + S3 (static)               │
│  SLA: 99.9% uptime (badge must never 404)           │
└─────────────────────────────────────────────────────┘
```

---

## Component Details

### API Gateway

- AWS API Gateway v2 (HTTP API)
- Rate limit: 100 req/min per API key (Pro), 500 req/min (Team), unlimited (Enterprise)
- Authentication: API key (header `X-Fynor-Key`) or JWT (dashboard sessions)
- Request validation: JSON schema validation before passing to orchestrator

### Check Orchestrator

- AWS ECS Fargate task (not Lambda — check runs can take up to 120 seconds)
- Receives `{target, interface_type, api_key, options}` from API Gateway
- Selects the correct adapter (MCPAdapter, RESTAdapter, etc.)
- Dispatches 8 check tasks concurrently (asyncio task group)
- Returns `ScorecardResult` to caller and writes to history store

### Check Workers

- Run inside the orchestrator process (not separate services)
- Each check is a Python async function — all 8 run concurrently per check run
- Timeout: 120 seconds hard limit per check run (enforced at orchestrator level)
- If a check times out, it returns score=0 with `detail="check timed out"`

### History Store

- **Hot storage:** DynamoDB table `fynor-check-results`
  - Partition key: `target_hash` (SHA256 of normalized target URL)
  - Sort key: `timestamp` (ISO 8601 UTC)
  - TTL: 90 days for Pro, 365 days for Enterprise
  - Global secondary index: `check_name` for cross-target check analysis

- **Cold storage:** S3 bucket `fynor-history-archive`
  - Parquet files partitioned by `year/month/target_hash/`
  - Lifecycle policy: Glacier after 2 years
  - Used by Pattern Detector (reads 30-day window from DynamoDB, never from S3)

### Certification Store

- DynamoDB table `fynor-certifications`
- One row per `(target, interface_type)` pair
- Fields: `status`, `consecutive_passing_days`, `last_check_date`, `cert_id`, `badge_url`
- Updated atomically after each check run that produces a grade ≥ B

### Badge + Cert Endpoints

- Pre-rendered SVG badges stored in S3, served via CloudFront
- Badge regenerated after every check run (grade or status change triggers S3 put)
- CloudFront CDN: global distribution, <50ms badge load time globally
- Badge URL format: `https://fynor.tech/badge/{cert_id}.svg`
- Cert JSON format: `https://fynor.tech/cert/{cert_id}.json`

---

## Environments

| Environment | Purpose | URL |
|-------------|---------|-----|
| `prod` | Live production | fynor.tech |
| `staging` | Pre-release validation | staging.fynor.tech |
| `dev` | Developer testing | dev.fynor.tech (internal only) |

Deployments to `prod` require:
1. All tests passing in CI (`pytest` + `ruff` + `mypy`)
2. Staging deployment validated (manual smoke test or `/qa` CI step)
3. No open critical security findings

---

## Scalability

### Burst Test Load

The most resource-intensive operation is the `rate_limit` check, which fires 50
requests at 20 req/s against the target. This runs from Fynor's ECS tasks, not
from the developer's machine.

**Concurrency model:**
- Each check run = 1 ECS Fargate task
- Up to 100 concurrent check runs (100 tasks)
- Auto-scaling: ECS scales up to 500 tasks under high load (CI/CD pipeline spikes)

**Egress cost:** 50 requests × ~1KB average payload = 50KB per check run.
At 10,000 check runs/day = 500MB/day egress. At AWS egress pricing of $0.09/GB:
**$45/month egress at 10K runs/day** — negligible relative to subscription revenue.

### Database Scalability

DynamoDB is provisioned with on-demand capacity. At 10,000 check runs/day × 8 checks
= 80,000 writes/day = ~1 write/second average. On-demand capacity handles burst spikes
(GitHub Action runs cluster at push time) without capacity planning.

---

## Security

- All check traffic originates from Fynor's AWS VPC (static IP range documented for clients who whitelist)
- API keys are hashed (bcrypt) before storage — raw keys never stored
- JSONL history is encrypted at rest (AES-256) in both DynamoDB and S3
- Phase C decision logs are encrypted with per-client KMS keys — Fynor operators cannot read client decision data
- SOC 2 Type II audit: target Month 24 (required before first Enterprise client onboards)

---

## Infrastructure as Code

All AWS resources are defined in Terraform (target: `infra/` directory, Month 10).
No manual resource creation in production.

| Resource | Terraform Module |
|----------|-----------------|
| API Gateway | `infra/modules/api-gateway` |
| ECS Cluster | `infra/modules/ecs-check-workers` |
| DynamoDB Tables | `infra/modules/dynamodb` |
| S3 Buckets | `infra/modules/s3-history` |
| CloudFront | `infra/modules/cdn-badges` |
| Lambda (Pattern Detector) | `infra/modules/lambda-intelligence` |

---

## Cost Model at Scale

| ARR Level | Monthly AWS Cost | Margin Impact |
|-----------|-----------------|---------------|
| $133K (Y1) | ~$800 | Negligible |
| $1M (Y3) | ~$4,500 | 0.5% of revenue |
| $10M (Y8) | ~$32,000 | 0.4% of revenue |
