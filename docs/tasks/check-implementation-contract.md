# Check Implementation Contract

**SDD Layer:** Task  
**Governs:** `fynor/checks/`, `tests/checks/`  
**Design source:** `docs/adr/ADR-03-check-taxonomy.md`, `docs/adr/ADR-04-threshold-justification.md`  
**Status:** Active  
**Last updated:** 2026-05-13

This document defines the implementation contract for every check in
`fynor/checks/`. An agent implementing or modifying a check must satisfy
every requirement in this document. All requirements are verifiable by
the test commands listed.

---

## Universal Check Contract

Every check function must satisfy ALL of the following. No exceptions.

### Return Type

```python
from fynor.checks.base import CheckResult

@dataclass
class CheckResult:
    score: int          # 0–100. 0 = critical failure. 100 = full pass.
    passed: bool        # True if score >= check-specific pass threshold
    detail: str         # Human-readable explanation, max 200 chars
    check_name: str     # Exact name from ADR-03 (e.g., "auth_token")
    duration_ms: int    # How long the check took in milliseconds
```

### Determinism Rule

Given the same target server state, the check must always return the same score.

**Prohibited patterns:**
- `random.*` calls
- `datetime.now()` comparisons inside scoring logic
- Any non-deterministic network retry that changes the score (retries that
  preserve the worst-case result are allowed)

**Allowed patterns:**
- Multiple requests for statistical stability (e.g., 20 requests for P95)
- Retrying on connection errors before recording a failure (max 3 retries,
  exponential backoff, but the final score reflects the observed failure)

### Error Handling

Checks must never raise unhandled exceptions. All network errors are caught
and converted to a score of 0 with a descriptive `detail`.

```python
# Correct
try:
    result = await client.get(url, timeout=10.0)
except httpx.TimeoutException:
    return CheckResult(score=0, passed=False,
                       detail="Connection timed out after 10s",
                       check_name=CHECK_NAME, duration_ms=10000)

# Wrong — propagates exception to caller
result = await client.get(url, timeout=10.0)  # can raise
```

### Timeout

Every check must complete within 60 seconds. The per-request timeout is 10
seconds (httpx `timeout=10.0`). If the check window (e.g., 20 requests)
exceeds 60 seconds total, abort with score=0.

### Verifiable by

```bash
pytest tests/checks/ -v --cov=fynor/checks --cov-report=term-missing
```

Coverage must be ≥ 90% for each check file individually.

---

## Check-Specific Contracts

### 1. `latency_p95`

**ADR-03 signal class:** Performance — latency tail  
**Pass threshold:** score ≥ 60 (P95 latency ≤ 500ms)

```
Scoring:
  P95 latency ≤ 200ms  → score = 100
  P95 latency ≤ 500ms  → score = 60 + ((500 - P95) / 300) * 40  (linear interpolation)
  P95 latency ≤ 1000ms → score = 20 + ((1000 - P95) / 500) * 40
  P95 latency > 1000ms → score = 0
```

**Implementation requirements:**
- Send exactly 20 HTTP GET requests to the target's health/probe endpoint
- Collect response times in milliseconds for all 20 requests
- Compute P95: sort the 20 values, take the 19th value (0-indexed)
- Requests are sequential (not concurrent) — concurrent requests would
  inflate latency artificially and misrepresent single-agent load patterns
- If fewer than 10 requests succeed, score = 0 (insufficient sample)

**Verifiable by:**
```bash
pytest tests/checks/test_latency_p95.py -v
# Must cover: fast server, slow server, timeout case, insufficient sample case
```

---

### 2. `error_rate`

**ADR-03 signal class:** Reliability — error budget  
**Pass threshold:** score ≥ 60 (error rate ≤ 5%)

```
Scoring:
  error_rate = 0%   → score = 100
  error_rate ≤ 1%   → score = 90
  error_rate ≤ 5%   → score = 60
  error_rate ≤ 10%  → score = 30
  error_rate > 10%  → score = 0

  Interpolate linearly within each band.
```

**Implementation requirements:**
- Send exactly 50 HTTP requests to the target using the standard probe payload
- An error is: HTTP 5xx, connection refused, timeout, or malformed JSON-RPC response
- HTTP 429 (rate limit) is NOT counted as an error — record it separately
- HTTP 4xx other than 429 IS counted as an error
- Window size of 50 is locked (ADR-04 justification: binomial variance at 5%
  error rate over n=50 is ±3.1%)

**Verifiable by:**
```bash
pytest tests/checks/test_error_rate.py -v
# Must cover: 0% errors, 5% errors, 10% errors, 100% errors, 429-excluded case
```

---

### 3. `schema`

**ADR-03 signal class:** Reliability — protocol conformance  
**Pass threshold:** score ≥ 60 (envelope valid, no required fields missing)

```
Scoring:
  All required fields present + correct types → score = 100
  Required fields present, minor type mismatch → score = 70
  Missing optional fields only               → score = 80
  Missing required fields                    → score = 0
  Not valid JSON                             → score = 0
  Not JSON-RPC 2.0 envelope                 → score = 0
```

**Implementation requirements:**
- Send a standard JSON-RPC 2.0 probe request:
  `{"jsonrpc": "2.0", "method": "ping", "id": 1}`
- Validate the response envelope: must have `jsonrpc`, `id`, and either
  `result` or `error` fields
- `jsonrpc` value must be exactly `"2.0"` (string, not float)
- `id` in response must match `id` in request
- MCP-specific fields beyond the JSON-RPC envelope are NOT validated here
  (they belong to a future `mcp_schema` check — see ADR-03 extensibility contract)
- Send 3 probe requests; score is the worst-case result (not average)

**Verifiable by:**
```bash
pytest tests/checks/test_schema.py -v
# Must cover: valid envelope, missing jsonrpc field, wrong version, id mismatch,
#             non-JSON response, error object response (still valid)
```

---

### 4. `retry`

**ADR-03 signal class:** Reliability — recovery behavior  
**Pass threshold:** score ≥ 60 (server handles malformed requests gracefully)

```
Scoring:
  Returns 400 with JSON-RPC error object  → score = 100
  Returns 400 with plain error text       → score = 70
  Returns 200 with JSON-RPC error object  → score = 60  (technically valid)
  Returns 500 on malformed input          → score = 20
  Server crashes / times out             → score = 0
```

**Implementation requirements:**
- Send a deliberately malformed JSON-RPC request:
  `{"jsonrpc": "2.0", "method": null, "id": 1}` (null method is invalid)
- Send a second malformed request with missing `id`:
  `{"jsonrpc": "2.0", "method": "test"}`
- Score is the average of the two sub-scores
- Purpose: verify server does not crash on bad input (agent pipelines send
  malformed requests during prompt injection attempts)

**Verifiable by:**
```bash
pytest tests/checks/test_retry.py -v
# Must cover: correct 400 response, 500 crash, 200 with error object, timeout
```

---

### 5. `auth_token`

**ADR-03 signal class:** Security — credential leakage  
**Pass threshold:** score = 100 (no credentials in response headers)

**Security cap rule (ADR-02):** If `auth_token` score == 0, the final grade
is capped at D regardless of other check scores. This is the only check
that can trigger the security cap.

```
Scoring:
  No credential headers in response    → score = 100
  Non-sensitive derived token present  → score = 70
  Credential-pattern header present    → score = 0
```

**Implementation requirements:**
- Send a standard probe request
- Inspect ALL response headers (case-insensitive)
- Check for headers matching `_SECRET_HEADER_PATTERNS`:
  `Authorization`, `X-API-Key`, `X-Secret`, `X-Token`, `X-Auth`,
  `X-Access-Token`, `X-Refresh-Token`, `Bearer`
- If a matching header is found: record its NAME only (never its value)
  in the `detail` field. The value must never be logged.
- If the header value looks like a derived/public token (UUID format,
  session ID format not matching credential patterns), score = 70

**Verifiable by:**
```bash
pytest tests/checks/test_auth_token.py -v
# Must cover: clean headers, credential header present (value never logged),
#             derived token case, security cap triggering in scorer
```

---

### 6. `rate_limit`

**ADR-03 signal class:** Security — resource exhaustion protection  
**Pass threshold:** score ≥ 60 (server enforces rate limiting)

```
Scoring:
  429 received within 50 requests at 20 req/s → score = 100
  429 received but only after > 50 requests   → score = 70
  No 429 received in burst window             → score = 0
```

**Implementation requirements:**
- Send 50 requests at 20 requests/second (rate = 50ms between requests)
- User-Agent header: `Fynor-Reliability-Checker/1.0`
- If a 429 is received at any point, record which request number triggered it
- The burst rate (20 req/s) is chosen to be well below DoS thresholds
  while being above normal human usage (T3 risk mitigation)
- If the server blocks Fynor's IP (connection refused after 429): score = 100
  (IP blocking is a valid rate-limiting implementation)

**Verifiable by:**
```bash
pytest tests/checks/test_rate_limit.py -v
# Must cover: 429 returned early, no 429 returned, IP block response
```

---

### 7. `timeout`

**ADR-03 signal class:** Performance — hanging connection  
**Pass threshold:** score ≥ 60 (server responds within 5s)

```
Scoring:
  Response received < 1s  → score = 100
  Response received < 3s  → score = 80
  Response received < 5s  → score = 60
  Response received < 10s → score = 20
  No response in 10s     → score = 0
```

**Implementation requirements:**
- Send a single request with a 10-second hard timeout
- Measure time-to-first-byte (TTFB), not time-to-complete
- Use `httpx` with `timeout=httpx.Timeout(connect=5.0, read=10.0)`
- If the connection is established but response body hangs, score = 20
  (server is alive but slow — different failure mode from total timeout)
- The 5-second pass threshold reflects agent pipeline requirements:
  an agent calling an MCP tool expects a response within its own timeout window

**Verifiable by:**
```bash
pytest tests/checks/test_timeout.py -v
# Must cover: fast response, 3s response, 5s response, 10s timeout, body-hang
```

---

### 8. `log_completeness`

**ADR-03 signal class:** Reliability — observability  
**Pass threshold:** score ≥ 60 (server exposes structured logs or metrics)

```
Scoring:
  Structured JSON logs on /logs or /metrics → score = 100
  Plain text logs accessible               → score = 70
  Health endpoint only (no logs)           → score = 40
  No observability endpoints found         → score = 0
```

**Implementation requirements:**
- Probe the following endpoints in order:
  `/logs`, `/metrics`, `/health`, `/.well-known/health`, `/status`
- For each endpoint that returns 200: check if response is JSON
- If JSON with `level` or `severity` fields: score = 100 (structured logs)
- If JSON without log fields but with metrics-like keys: score = 80
- If plain text (200, not JSON): score = 70
- If only `/health` returns 200 with no log data: score = 40
- If no endpoint returns 200: score = 0
- Non-standard endpoints (e.g., `/api/logs`) are not probed — servers must
  expose observability on standard paths (documented in Fynor's integration guide)

**Verifiable by:**
```bash
pytest tests/checks/test_log_completeness.py -v
# Must cover: JSON logs, plain text logs, health-only, no endpoints found
```

---

## Adding a New Check

Adding a check beyond the current 8 requires:

1. A taxonomy entry in `docs/adr/ADR-03-check-taxonomy.md` — signal class,
   agent-specific failure mode, rejected alternatives
2. A threshold justification in `docs/adr/ADR-04-threshold-justification.md`
   — statistical basis for pass threshold and scoring bands
3. An entry in this file (check-implementation-contract.md)
4. Scoring weight allocation — requires an ADR-02 amendment (weights are locked)
5. Tests covering all scoring bands and edge cases

A PR introducing a new check without all five items will be rejected.
