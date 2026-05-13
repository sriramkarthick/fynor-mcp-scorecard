# Fynor Hosted API — Specification

**Base URL:** `https://api.fynor.tech/v1`  
**Authentication:** `X-Fynor-Key: <your-api-key>` header  
**Content-Type:** `application/json`  
**Version:** v1 (target: Month 12)

---

## Authentication

All API endpoints require an API key. Keys are tied to a Fynor account and a specific tier.

```
X-Fynor-Key: fynor_live_xxxxxxxxxxxxxxxxxxxx
```

API keys are generated in the Fynor dashboard. Never include API keys in URL parameters.

---

## Endpoints

### POST /check

Run a reliability check against a target interface.

**Request:**
```json
{
  "target": "https://your-mcp-server.com/mcp",
  "type": "mcp",
  "options": {
    "auth_token": "Bearer your-token",
    "timeout_ms": 5000,
    "checks": ["latency_p95", "auth_token", "schema"]
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target` | string | Yes | Full URL of the interface to check |
| `type` | enum | Yes | `mcp` \| `rest` \| `graphql` \| `grpc` \| `websocket` \| `soap` \| `cli` |
| `options.auth_token` | string | No | Auth token to include in check requests |
| `options.timeout_ms` | integer | No | Per-request timeout (default: 5000) |
| `options.checks` | string[] | No | Subset of checks to run (default: all 8) |

**Response 200:**
```json
{
  "run_id": "run_01HXYZ...",
  "target": "https://your-mcp-server.com/mcp",
  "type": "mcp",
  "grade": "B",
  "weighted_score": 81.5,
  "security_score": 100.0,
  "reliability_score": 72.0,
  "performance_score": 80.0,
  "security_capped": false,
  "checks": [
    {
      "check": "latency_p95",
      "passed": true,
      "score": 100,
      "value": 340.0,
      "detail": "P95 latency: 340ms over 20 requests."
    },
    {
      "check": "error_rate",
      "passed": false,
      "score": 40,
      "value": 0.082,
      "detail": "Error rate: 8.2% (4/50 requests failed)."
    }
  ],
  "timestamp": "2026-05-13T10:23:44Z",
  "duration_ms": 67420
}
```

**Response 402 (tier limit exceeded):**
```json
{
  "error": "target_limit_exceeded",
  "message": "Pro plan allows 5 monitored targets. Upgrade to Team for 25 targets.",
  "upgrade_url": "https://fynor.tech/upgrade"
}
```

---

### GET /history

Retrieve check history for a target.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | string | Filter by target URL (required unless `check` specified) |
| `check` | string | Filter by check name |
| `last` | integer | Return last N results (default: 20, max: 500) |
| `since` | ISO 8601 | Return results since this timestamp |

**Request:**
```
GET /history?target=https://your-mcp-server.com/mcp&last=10
```

**Response 200:**
```json
{
  "target": "https://your-mcp-server.com/mcp",
  "count": 10,
  "results": [
    {
      "run_id": "run_01HXYZ...",
      "timestamp": "2026-05-13T10:23:44Z",
      "grade": "B",
      "weighted_score": 81.5,
      "checks": [...]
    }
  ]
}
```

---

### GET /patterns

Retrieve detected patterns for a target.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | string | Filter by target URL |
| `status` | enum | `pending` \| `confirmed` \| `rejected` |
| `type` | enum | `co_failure` \| `latency_drift` \| `time_signature` |

**Response 200:**
```json
{
  "target": "https://your-mcp-server.com/mcp",
  "patterns": [
    {
      "pattern_id": "pat_01ABC...",
      "pattern_type": "time_signature",
      "checks_involved": ["auth_token", "error_rate"],
      "confidence": 0.91,
      "description": "Failures cluster at hour 02:00 UTC (18 failures = 4.3x expected rate).",
      "evidence": {
        "hot_hour": 2,
        "failure_count": 18,
        "expected_rate": 4.17,
        "multiplier": 4.32
      },
      "detected_at": "2026-05-12T03:15:00Z",
      "status": "pending"
    }
  ]
}
```

---

### GET /cert/{cert_id}

Retrieve an Agent-Ready certificate.

**Response 200:**
```json
{
  "cert_id": "cert_01XYZ...",
  "target": "https://your-mcp-server.com/mcp",
  "interface_type": "mcp",
  "status": "certified",
  "grade": "A",
  "consecutive_passing_days": 47,
  "issued_date": "2026-04-15T00:00:00Z",
  "last_check_date": "2026-05-13T06:00:00Z",
  "badge_url": "https://fynor.tech/badge/cert_01XYZ.svg",
  "cert_url": "https://fynor.tech/cert/cert_01XYZ",
  "badge_markdown": "[![Fynor Agent-Ready](https://fynor.tech/badge/cert_01XYZ.svg)](https://fynor.tech/cert/cert_01XYZ)"
}
```

**Response 404:**
```json
{
  "error": "cert_not_found",
  "message": "No certificate found for this ID."
}
```

---

### GET /targets

List monitored targets for the authenticated account.

**Response 200:**
```json
{
  "targets": [
    {
      "target": "https://your-mcp-server.com/mcp",
      "type": "mcp",
      "last_check": "2026-05-13T06:00:00Z",
      "last_grade": "B",
      "cert_status": "pending",
      "consecutive_passing_days": 12
    }
  ],
  "count": 1,
  "limit": 5,
  "plan": "pro"
}
```

---

## Webhooks

Fynor can POST check results to your endpoint after each run.

**Configuration:** Set in dashboard under Settings → Webhooks.

**Payload:**
```json
{
  "event": "check.completed",
  "run_id": "run_01HXYZ...",
  "target": "https://your-mcp-server.com/mcp",
  "grade": "B",
  "weighted_score": 81.5,
  "grade_changed": false,
  "cert_status_changed": false,
  "timestamp": "2026-05-13T10:23:44Z"
}
```

**Events:**
- `check.completed` — every check run
- `check.grade_changed` — grade changed from previous run
- `cert.issued` — target earned Agent-Ready certification
- `cert.suspended` — check failed, certification suspended
- `cert.revoked` — security check failed, certification revoked

---

## Rate Limits

| Tier | Check runs/hour | History requests/hour | Badge requests |
|------|----------------|----------------------|----------------|
| Pro | 12 | 120 | Unlimited |
| Team | 60 | 600 | Unlimited |
| Enterprise | Unlimited | Unlimited | Unlimited |

Rate limit headers on every response:
```
X-Fynor-RateLimit-Remaining: 8
X-Fynor-RateLimit-Reset: 1715600400
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `unauthorized` | 401 | Missing or invalid API key |
| `forbidden` | 403 | API key valid but insufficient tier permissions |
| `target_limit_exceeded` | 402 | Plan target limit reached |
| `rate_limit_exceeded` | 429 | Check run rate limit exceeded |
| `target_unreachable` | 422 | Target URL did not respond during check |
| `invalid_interface_type` | 400 | Unknown `type` value |
| `check_timeout` | 504 | Check run exceeded 120-second hard timeout |
| `internal_error` | 500 | Fynor infrastructure error — retryable |

---

## SDK Support (Roadmap)

| Language | Target Month |
|----------|-------------|
| Python (fynor-sdk) | Month 14 |
| TypeScript/Node | Month 16 |
| Go | Month 20 |
