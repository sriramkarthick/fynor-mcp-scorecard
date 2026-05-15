# Cloudflare Rate Limiting Setup — Fynor Phase A

**Decision:** D4 (plan-eng-review 2026-05-15)  
**Why:** Cloudflare is the primary rate limiter, running before traffic reaches Railway.
If DynamoDB (the secondary rate limiter) is unavailable, Cloudflare still blocks floods
independently. "Fail open" on DynamoDB alone = an attacker can disable rate limiting
by flooding DynamoDB. Cloudflare cannot be disabled by flooding DynamoDB.

---

## Prerequisites

1. `fynor.tech` added to Cloudflare (free plan is sufficient)
2. Railway service deployed and accessible (get the `.up.railway.app` CNAME)
3. DNS nameservers for `fynor.tech` pointing to Cloudflare

---

## Step 1 — Point DNS at Railway (proxied)

In Cloudflare dashboard → DNS → Records:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `api` | `<your-service>.up.railway.app` | ✅ Proxied (orange cloud) |

**Critical:** The record MUST be proxied (orange cloud). Grey cloud = DNS-only =
traffic bypasses Cloudflare = rate limiting is disabled.

Verify proxy is active:
```bash
curl -I https://api.fynor.tech/health
# Look for: cf-ray: <id>  ← confirms Cloudflare is in the path
```

---

## Step 2 — Create rate limit rule (Cloudflare dashboard)

Security → WAF → Rate limiting rules → Create rule:

**Rule 1: POST /check primary rate limit**

| Field | Value |
|-------|-------|
| Name | `fynor-check-rate-limit` |
| If incoming requests match | Custom filter expression |
| Expression | `(http.request.method eq "POST" and http.request.uri.path contains "/check")` |
| Characteristics | IP Source Address |
| Period | 30 seconds |
| Requests | 100 |
| Action | Block |
| Duration | 60 seconds |

**Rule 2: API backstop (all /api/ paths)**

| Field | Value |
|-------|-------|
| Name | `fynor-api-backstop` |
| Expression | `http.request.uri.path starts_with "/api/"` |
| Characteristics | IP Source Address |
| Period | 60 seconds |
| Requests | 500 |
| Action | Block |
| Duration | 120 seconds |

---

## Step 3 — Verify rate limiting is active

```bash
# Should get 200 OK
curl -X POST https://api.fynor.tech/check \
  -H "Content-Type: application/json" \
  -d '{"target":"https://example.com","type":"rest"}'

# Flood test (requires wrk or hey — do this from a test IP, not production)
# After 100 requests in 30s, next request should return HTTP 429
hey -n 110 -c 10 -m POST https://api.fynor.tech/check \
  -H "Content-Type: application/json" \
  -d '{"target":"https://example.com","type":"rest"}'
# Expected: first ~100 return 200/422, remaining return 429
```

---

## Step 4 — Configure FastAPI to trust Cloudflare IP headers

Railway sees Cloudflare's IP (not the real client IP). The real client IP is in:
`CF-Connecting-IP` (Cloudflare proprietary header)

In `fynor/api/main.py` (when FastAPI is implemented in Month 4):

```python
from fastapi import FastAPI, Request
import os

app = FastAPI()

def get_client_ip(request: Request) -> str:
    """
    Extract real client IP from Cloudflare proxy header.
    Falls back to direct connection IP (for local dev / staging without CF).
    """
    trusted_header = os.environ.get("TRUSTED_PROXY_HEADER", "")
    if trusted_header and trusted_header in request.headers:
        return request.headers[trusted_header]
    return request.client.host if request.client else "unknown"
```

Set in Railway dashboard: `TRUSTED_PROXY_HEADER=CF-Connecting-IP`

---

## Step 5 — Terraform (Phase B, Month 10)

When infrastructure moves to Terraform, apply the managed config:

```bash
cd infra/cloudflare
terraform init
terraform plan -var="cloudflare_api_token=$CF_API_TOKEN" \
               -var="cloudflare_zone_id=$CF_ZONE_ID" \
               -var="railway_cname=<your-service>.up.railway.app"
terraform apply
```

The Terraform config in `main.tf` is the source of truth for Phase B onwards.
Dashboard rules created manually in Phase A should be deleted once Terraform
manages the same rules (to avoid duplication).

---

## Rate Limit Decision Log

| Threshold | Rationale |
|-----------|-----------|
| 100 req / 30s per IP | One check every 0.3s — far above any legitimate use case (checks take ~45s to complete). A user running checks legitimately would hit at most 1 req/45s = ~2 req/30s. 100/30s gives 50× headroom before blocking. |
| Block duration: 60s | Long enough to break automated flood scripts; short enough that a user who accidentally hits the limit can retry within 1 minute. |
| API backstop 500 req/60s | Covers non-check endpoints (health, results polling). 500 req/min per IP is ~8 req/s — reasonable for a dashboard polling for results. |

---

## Dependency: DynamoDB secondary rate limiter

Cloudflare (primary) and DynamoDB (secondary) work in layers:

```
Internet
  │
  ▼ Cloudflare blocks at 100/30s (IP-level, no DB dependency)
  │
  ▼ Railway / FastAPI
  │
  ▼ DynamoDB secondary check: PK=ratelimit#{ip_hash}, TTL=now+30s
    (catches cases where Cloudflare passes a request that shouldn't proceed,
     e.g. same IP from different Cloudflare PoPs counted separately)
```

If DynamoDB is down: Cloudflare primary still blocks floods. The system
degrades gracefully — DynamoDB being unavailable does NOT open the gate.
