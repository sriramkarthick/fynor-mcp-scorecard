# API Implementation Contract

**SDD Layer:** Task  
**Governs:** `fynor/api/`, `infrastructure/lambdas/`, `infrastructure/terraform/`  
**Design source:** `docs/api-specification.md`, `docs/deployment-architecture.md`  
**Status:** Active — Month 4 onwards  
**Last updated:** 2026-05-13

This document defines the implementation contracts for the Fynor hosted API.
Covers FastAPI app structure, Lambda fan-out architecture, DynamoDB schema,
and authentication. Do not implement anything in this document before
Month 4 (see `docs/tasks/build-sequence.md`).

**Decision basis:** D2 (async workers), D3 (DynamoDB), D5 (FastAPI), D7 (Lambda per check).

---

## Framework Contract

**Framework:** FastAPI (not Flask, not Django)  
**Python version:** 3.11+  
**Async:** All endpoints must be `async def`  
**Validation:** Pydantic v2 for all request/response models

```python
# Every endpoint follows this pattern
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Fynor Reliability API",
    version="0.1.0",
    docs_url="/docs",          # OpenAPI UI — always enabled
    redoc_url="/redoc",
)
```

**Verifiable by:**
```bash
pytest tests/api/ -v
uvicorn fynor.api.main:app --host 0.0.0.0 --port 8000
# GET /docs returns 200 with OpenAPI schema
# GET /health returns {"status": "ok", "version": "0.1.0"}
```

---

## Endpoint Contracts

All endpoints must match the schemas in `docs/api-specification.md` exactly.
Pydantic models are the single source of truth — the OpenAPI spec is generated
from them, not maintained separately.

### POST /check

**Purpose:** Submit a check run. Returns immediately with a `job_id`.

```python
class CheckRequest(BaseModel):
    target_url: HttpUrl
    interface_type: Literal["mcp", "rest"] = "mcp"
    checks: list[CheckName] | None = None  # None = all 8 checks
    webhook_url: HttpUrl | None = None

class CheckResponse(BaseModel):
    job_id: str          # UUID v4
    status: Literal["queued"]
    estimated_duration_s: int = 60
    poll_url: str        # GET /check/{job_id}

# Contract:
# - Must return within 1 second
# - Must invoke orchestrator Lambda before returning
# - job_id must be persisted to DynamoDB before returning (so poll works immediately)
```

**Verifiable by:**
```bash
pytest tests/api/test_check_endpoint.py -v -k "test_post_check"
# Must verify: response time < 1s, job_id in DynamoDB, 401 without API key
```

### GET /check/{job_id}

**Purpose:** Poll for check result.

```python
class CheckResultResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    target_url: str | None = None
    grade: Literal["A", "B", "C", "D", "F"] | None = None
    weighted_score: float | None = None
    security_capped: bool | None = None
    checks: dict[CheckName, CheckDetail] | None = None
    completed_at: datetime | None = None

# Contract:
# - Must return within 200ms (DynamoDB read, no computation)
# - If job_id not found: 404
# - If job belongs to different API key: 403
```

### GET /history

```python
class HistoryRequest(BaseModel):  # query params
    target_url: HttpUrl | None = None
    limit: int = 10               # max 100
    since: datetime | None = None

# Contract:
# - Returns only runs belonging to the authenticated API key
# - Sorted by completed_at DESC
# - DynamoDB query on target_hash GSI, filtered by api_key_hash
```

### GET /cert/{id}

```python
class CertResponse(BaseModel):
    cert_id: str
    target_url: str
    grade: Literal["A", "B", "C", "D", "F"]
    cert_status: Literal["CERTIFIED", "PENDING", "SUSPENDED", "REVOKED"]
    issued_at: datetime | None
    valid_until: datetime | None
    consecutive_passing_days: int
    badge_url: str   # CloudFront SVG URL

# Contract:
# - cert/{id} is publicly readable (no auth required) — badges embed this
# - The badge_url must resolve to an SVG within 200ms
```

### GET /targets

```python
class TargetSummary(BaseModel):
    target_url: str
    interface_type: str
    cert_status: str
    last_grade: str | None
    last_checked_at: datetime | None

# Contract:
# - Returns only targets belonging to the authenticated API key
# - Limit 100 targets per account on Pro tier
```

---

## Lambda Fan-Out Architecture

**Decision basis:** D7 (Lambda per check, not ECS Fargate, not inline threads)

```
POST /check
    │
    ▼
FastAPI (ECS or Lambda) → writes job to DynamoDB (status=queued)
    │
    ▼
Orchestrator Lambda (invoked async)
    │
    ├── invoke Lambda: latency_p95_check
    ├── invoke Lambda: error_rate_check
    ├── invoke Lambda: schema_check
    ├── invoke Lambda: retry_check
    ├── invoke Lambda: auth_token_check
    ├── invoke Lambda: rate_limit_check
    ├── invoke Lambda: timeout_check
    └── invoke Lambda: log_completeness_check
              │
              ▼ (all 8 complete)
         Orchestrator aggregates results
              │
              ▼
         Scorer Lambda → computes weighted_score + grade
              │
              ▼
         DynamoDB: status=completed, results stored
              │
              ▼
         Webhook Lambda (if webhook_url set) → fires check.completed
```

### Orchestrator Lambda Contract

```python
# infrastructure/lambdas/orchestrator.py

def handler(event: dict, context: Any) -> dict:
    """
    Input event:
    {
        "job_id": str,
        "target_url": str,
        "interface_type": "mcp" | "rest",
        "checks": list[str]  # check names to run
    }

    Invokes all requested check Lambdas concurrently using boto3
    invoke(InvocationType='RequestResponse').

    Aggregates results, invokes scorer, writes final result to DynamoDB.

    Returns: {"job_id": str, "status": "completed" | "failed"}
    """
```

**Constraints:**
- All 8 check Lambdas must be invoked concurrently (not sequentially)
- Orchestrator timeout: 120 seconds (Lambda max for this use case)
- Each check Lambda timeout: 30 seconds
- If any check Lambda times out: that check receives score=0, detail="Lambda timeout"
- Orchestrator must update DynamoDB status to "running" before invoking checks
- Orchestrator must update DynamoDB status to "completed" or "failed" after aggregation

**Verifiable by:**
```bash
pytest tests/infrastructure/test_orchestrator.py -v
# Must verify: concurrent invocation, timeout handling, DynamoDB status updates
# Use moto for DynamoDB mocking, moto for Lambda mocking
```

### Per-Check Lambda Contract

```python
# infrastructure/lambdas/checks/latency_p95.py (and 7 others)

def handler(event: dict, context: Any) -> dict:
    """
    Input: {"target_url": str, "job_id": str}
    Output: {"check_name": str, "score": int, "passed": bool,
             "detail": str, "duration_ms": int}

    Invokes fynor.checks.latency_p95.run(target_url).
    Catches ALL exceptions — never raises.
    """
```

**Constraints:**
- Lambda must import from `fynor.checks.*` — no logic duplication
- Lambda package must include `fynor` package (Lambda layer or inline)
- Cold start budget: 2 seconds (Python 3.11 with httpx loads fast)
- Memory: 256MB per check Lambda (httpx + fynor package fits in 128MB,
  256MB gives headroom and reduces cold start time)

---

## DynamoDB Schema Contract

**Decision basis:** D3 (DynamoDB, not Postgres)

### Table: `fynor-check-runs`

```
Partition key: target_hash (SHA-256 of target_url, hex string)
Sort key:      timestamp (ISO 8601, e.g., "2026-05-13T14:23:00Z")

Required attributes:
  job_id        String   UUID v4
  target_url    String   Original URL
  api_key_hash  String   bcrypt hash prefix (first 7 chars of hash for lookup)
  status        String   "queued" | "running" | "completed" | "failed"
  grade         String   "A" | "B" | "C" | "D" | "F" (null until completed)
  weighted_score Number  0.0–100.0 (null until completed)
  check_results Map      {check_name: {score, passed, detail, duration_ms}}
  created_at    String   ISO 8601
  completed_at  String   ISO 8601 (null until completed)
  TTL           Number   Unix timestamp for auto-expiry (set by tier)

TTL values by tier:
  Free:       created_at + 0 (CLI only, no server storage)
  Pro:        created_at + 7776000s (90 days)
  Team:       created_at + 15552000s (180 days)
  Enterprise: created_at + 31536000s (365 days)
```

### GSI: `api-key-index`

```
Partition key: api_key_hash
Sort key:      timestamp

Purpose: GET /history queries — "give me all runs for this API key"
```

### Table: `fynor-certifications`

```
Partition key: target_hash
Sort key:      "CERT" (literal — only one cert record per target)

Required attributes:
  cert_id             String   UUID v4
  target_url          String
  cert_status         String   "PENDING" | "CERTIFIED" | "SUSPENDED" | "REVOKED"
  grade               String   Grade at certification time
  issued_at           String   ISO 8601 (null until CERTIFIED)
  valid_until         String   ISO 8601 (null until CERTIFIED)
  consecutive_days    Number   Count of consecutive passing days
  last_evaluated_at   String   ISO 8601 (when the cron last ran)
  api_key_hash        String   Owner's key hash
```

### Table: `fynor-daily-results`

```
Partition key: target_hash
Sort key:      date (YYYY-MM-DD, e.g., "2026-05-13")

Purpose: Certification loop (see certification-loop-contract.md)
  Stores one pass/fail record per target per day.
  TTL: 45 days (keeps 30-day window + 15 days buffer)

Required attributes:
  passed          Boolean
  grade           String
  fynor_infra_err Boolean   True if Fynor's infrastructure caused the failure
  runs_count      Number    How many check runs happened this day
```

**Verifiable by:**
```bash
pytest tests/storage/ -v
# Uses moto for DynamoDB mocking
# Must verify: TTL set correctly by tier, GSI queryable, all attributes present
```

---

## Authentication Contract

**API key storage:** bcrypt hash (cost factor 12) — raw key never stored.

```python
# fynor/api/auth.py

import bcrypt
import secrets

def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key, hashed_key). Store only hashed_key."""
    raw = "fynor_" + secrets.token_urlsafe(32)
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt(rounds=12)).decode()
    return raw, hashed

def verify_api_key(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode(), hashed.encode())

# FastAPI dependency
async def get_current_account(
    authorization: str = Header(...),
    db: DynamoDBClient = Depends(get_db),
) -> Account:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    raw_key = authorization[7:]
    # Look up by api_key_hash prefix (first 7 chars), then verify full hash
    ...
```

**Constraints:**
- Raw API key is delivered to user exactly once (on creation), then discarded
- bcrypt cost factor 12 → ~300ms verification time on Lambda — acceptable
- API keys begin with `fynor_` prefix for easy identification in logs
- Compromised key rotation: new key generated, old hash deleted from DynamoDB

**Verifiable by:**
```bash
pytest tests/api/test_auth.py -v
# Must verify: no raw key stored, 401 on missing/invalid key,
#              403 on key that belongs to different account
```

---

## Rate Limiting Contract

**Decision basis:** Tier-based limits from `docs/api-specification.md`.

```python
# fynor/api/middleware/rate_limit.py

RATE_LIMITS = {
    "free":       0,   # CLI only, no hosted API
    "pro":        12,  # runs per hour
    "team":       60,  # runs per hour
    "enterprise": -1,  # unlimited
}

# Implementation: DynamoDB counter with 1-hour TTL
# Key: f"ratelimit:{api_key_hash}:{current_hour_iso}"
# On each POST /check:
#   1. Increment counter
#   2. If counter > limit: return 429 with Retry-After header
#   3. If counter == 1: set TTL to end of current hour
```

**Verifiable by:**
```bash
pytest tests/api/test_rate_limiting.py -v
# Must verify: 12th request succeeds, 13th returns 429 for Pro tier,
#              Retry-After header present on 429
```

---

## Webhook Contract

```python
# fynor/api/webhooks.py

# Webhook payload for check.completed event:
{
    "event": "check.completed",
    "job_id": "uuid",
    "target_url": "https://...",
    "grade": "A",
    "weighted_score": 92.5,
    "security_capped": False,
    "timestamp": "2026-05-13T14:23:45Z",
    "fynor_signature": "sha256=<hmac-sha256 of payload body>"
}

# Signature: HMAC-SHA256 of raw request body using user's webhook secret
# User verifies: hmac.compare_digest(computed, header_value)
# Delivery: async Lambda, 3 retries with exponential backoff
# Timeout: 10s per delivery attempt
```

**Verifiable by:**
```bash
pytest tests/api/test_webhooks.py -v
# Must verify: signature correct, retry on 5xx response, 3-attempt limit
```

---

## Quality Gate

```bash
# All must pass before any hosted API PR merges
ruff check fynor/api/ infrastructure/
mypy fynor/api/ --strict
pytest tests/api/ tests/infrastructure/ tests/storage/ \
  --cov=fynor/api --cov=infrastructure \
  --cov-fail-under=90 -v
```
