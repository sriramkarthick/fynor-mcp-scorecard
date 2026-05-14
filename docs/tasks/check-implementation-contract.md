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
from fynor.history import CheckResult

@dataclass
class CheckResult:
    check: str                      # Exact name from ADR-03 (e.g., "auth_token")
    passed: bool                    # True if score >= check-specific pass threshold
    score: int                      # 0–100. 0 = critical failure. 100 = full pass.
    value: float | str | None = None  # Raw measured value (ms, %, count — check-specific)
    detail: str = ""               # Human-readable explanation (max 500 chars)
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
Scoring (step function — no interpolation):
  P95 latency ≤ 200ms  → score = 100
  P95 latency ≤ 500ms  → score = 80
  P95 latency ≤ 1000ms → score = 60   ← pass threshold
  P95 latency > 1000ms → score = 0
```

**Rationale for step function (not linear interpolation):** Linear scoring
creates non-determinism under floating-point arithmetic and makes pass/fail
thresholds ambiguous. Step functions produce identical scores for equivalent
server states and are easier to test exhaustively. (ADR-04 justification.)

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
Scoring (step function — no interpolation):
  error_rate = 0%    → score = 100
  error_rate ≤ 1%    → score = 90
  error_rate ≤ 5%    → score = 60   ← pass threshold (≤5%)
  error_rate ≤ 10%   → score = 30
  error_rate > 10%   → score = 0
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
Scoring (per probe; final = average of two probes):
  Returns 400 with JSON-RPC error object  → score = 100
  Returns 400 with plain error text       → score = 80
  Returns 200 with JSON-RPC error object  → score = 60   ← pass threshold
  Returns 2xx with no error object        → score = 20
  Returns 5xx / times out                → score = 0
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
Scoring (failure-count model):
  0 failures → score = 100   ← passed
  1 failure  → score = 40    ← failed
  2 failures → score = 10    ← failed
  3 failures → score = 0     ← failed + security cap triggers

Failure conditions (each counts as one failure):
  F1. Credential-pattern header found in response
  F2. Unauthenticated request returns 200 (or non-401/403)
  F3. Secret found as plaintext URL query parameter (e.g., ?api_key=…)
```

**Implementation requirements:**
- Send a standard probe request; inspect ALL response headers case-insensitively
- Check for headers matching `_SECRET_HEADER_PATTERNS`:
  `X-API-Key`, `X-Secret`, `X-Token`, `X-Auth`, `X-Access-Token`,
  `X-Refresh-Token` (NOT `Authorization` — that is a request header, not a
  response header; servers that echo it back are already caught by the pattern)
- If a matching header is found: record its NAME only (never its value)
  in the `detail` field. The value must **never** be logged — enforced by test.
- Also send one unauthenticated probe (no auth headers); 401 or 403 → pass.
  Any 2xx status → failure F2.
- Inspect `adapter.target` URL query params for credential-like param names
  (`api_key`, `token`, `secret`, `key`, `password`); if found → failure F3.
  Record only the param NAME, never its value.

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
  429 received + Retry-After header present  → score = 100   ← passed
  429 received, no Retry-After header        → score = 60    ← passed
  No 429 received in burst window            → score = 30    ← failed
  5xx errors received without any 429        → score = 0     ← failed
  5xx + 429 present: 429 takes precedence (score per Retry-After rule above)
```

**Implementation requirements:**
- Send 50 requests at 20 requests/second (rate = 50ms between requests)
- User-Agent header: `Fynor-Reliability-Checker/1.0`
- If a 429 is received at any point, record which request number triggered it
  in `detail` (e.g., "First 429 at request #12")
- Check first 429 response for `Retry-After` header (case-insensitive)
- The burst rate (20 req/s) is chosen to be well below DoS thresholds
  while being above normal human usage (T3 risk mitigation)
- `result.value` is the integer count of 429 responses received

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
  Response received ≤ 2000ms → score = 100   ← fast (passed)
  Response received ≤ 5000ms → score = 75    ← slow but alive (passed)
  Hard timeout (error contains "timeout")    → score = 0     ← failed
  Non-timeout connection error               → score = 75    ← graceful degradation
```

**Implementation requirements:**
- Use a tight adapter (connect_timeout=2.0s, read_timeout=5.0s) — separate
  from the standard 10s adapter used by other checks
- A "hard timeout" means the response error string contains the word "timeout"
- A non-timeout connection error (e.g., "connection refused") is not a timeout
  failure; it scores 75 as "graceful degradation confirmed" — the server is
  not hanging, it is just unreachable
- `result.value` is the measured latency in milliseconds, or `None` on timeout
- The 2-second threshold reflects agent pipeline SLAs — most orchestrators
  give tools a 2–3s budget before marking a step as slow

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
  JSON log body + timestamp field present   → score = 100   ← passed
  JSON log body, no timestamp field         → score = 70    ← passed
  Plain text log body (non-JSON, 200 OK)    → score = 60    ← passed
  Health/metrics endpoint only (no logs)    → score = 40    ← failed (not an audit log)
  No observability endpoint found           → score = 0     ← failed
```

**Implementation requirements:**
- Probe **log paths** first: `/logs`, `/audit`, `/audit-log`, `/events`, `/v1/logs`
- If no log path returns 200, probe **health/observability paths**:
  `/metrics`, `/health`, `/.well-known/health`, `/status`
- `result.value` is the path that returned 200 (e.g., `"/logs"`)
- Timestamp field detection: key name (case-insensitive) contains any of:
  `timestamp`, `ts`, `time`, `datetime`, `created_at`, `logged_at`
- For list responses (JSON array), extract keys from the first element
- Non-standard paths (e.g., `/api/logs`) are not probed — servers must
  expose observability on standard paths (documented in the integration guide)

**Verifiable by:**
```bash
pytest tests/checks/test_log_completeness.py -v
# Must cover: JSON logs, plain text logs, health-only, no endpoints found
```

---

---

### 9. `data_freshness`

**ADR-03 signal class:** Reliability — data currency  
**Pass threshold:** score ≥ 60 (data age ≤ 24 hours)

```
Scoring (step function — no interpolation):
  No timestamp field detected in response    → score = 0
  Timestamp present, data age > 24h         → score = 20
  Timestamp present, data age ≤ 24h         → score = 60   ← pass threshold
  Timestamp present, data age ≤ 60 min      → score = 80
  Timestamp present, data age ≤ 5 min       → score = 100
```

**Implementation requirements:**
- Send one HTTP probe via `adapter.call()`
- Recursively search response body (depth ≤ 4) for timestamp field names (case-insensitive):
  `timestamp`, `ts`, `time`, `datetime`, `created_at`, `logged_at`, `event_time`,
  `occurred_at`, `recorded_at`, `updated_at`, `modified_at`, `generated_at`,
  `fetched_at`, `collected_at`, `observed_at`
- Accept both ISO 8601 strings and Unix epoch integers/floats (milliseconds if value > 1e12)
- `result.value` is the data age in minutes (float), or `None` if no timestamp found
- `result.detail` must include the detected field name when a timestamp is found

**Verifiable by:**
```bash
pytest tests/checks/test_data_freshness.py -v
# Must cover: 5min, 60min, 24h, stale, no-timestamp, nested-timestamp, epoch format
```

---

### 10. `tool_description_quality`

**ADR-03 signal class:** Reliability — tool discoverability  
**Pass threshold:** score ≥ 60 (all tools have name + description ≥10 chars)

```
Scoring (worst-case across all tools):
  All tools: name + description ≥50 chars + typed inputSchema  → score = 100
  All tools: name + description ≥20 chars + inputSchema present → score = 80
  All tools: name + description ≥10 chars (no inputSchema)      → score = 60  ← pass
  Any tool:  description absent or < 10 chars                   → score = 20
  No tools returned / call fails / any tool missing name        → score = 0
```

**Implementation requirements:**
- Send `{"jsonrpc":"2.0","method":"tools/list","id":1,"params":{}}` via `adapter.call(payload=...)`
- Handle both `{"result":{"tools":[...]}}` and `{"result":[...]}` response shapes
- Score each tool individually; final score = minimum across all tool scores
- `inputSchema` typed parameters: all entries in `properties{}` must have a `type` field
- `result.value` is the count of fully-described tools (description ≥50 chars + typed inputSchema)
- `result.detail` must list names of inadequate tools (score < 80) if any

**Verifiable by:**
```bash
pytest tests/checks/test_tool_description_quality.py -v
# Must cover: full descriptions, adequate, description-only, short desc, empty list, worst-case
```

---

### 11. `response_determinism`

**ADR-03 signal class:** Reliability — structural consistency  
**Pass threshold:** score ≥ 60 (at least 2 of 3 probes structurally identical)

```
Scoring:
  All 3 probes have identical structural fingerprint  → score = 100
  Exactly 2 of 3 probes agree on fingerprint         → score = 60  ← pass threshold
  All 3 probes have different fingerprints            → score = 0
  Any probe fails (error / empty body)                → score = 0
```

**Implementation requirements:**
- Send exactly 3 sequential probes via `adapter.call()`
- Compute a structural fingerprint of each response body: recursively collect keys and value types (not values), sorted canonically, depth-limited to 3 levels
- Compare fingerprints using plurality vote; `most_common_count` = agreement count
- Value equality is NOT checked — only structural schema (keys + types)
- `result.value` is the plurality count (0–3)
- `result.detail` must identify which probe(s) diverged when score < 100

**Verifiable by:**
```bash
pytest tests/checks/test_response_determinism.py -v
# Must cover: all identical, 2-of-3 agree, all different, probe error, value-change-ok
```

---

### Amendment to `auth_token` — Failure Condition F4

The `auth_token` check now tests four failure conditions (up from three):

```
F1. Credential-pattern header found in response
F2. Unauthenticated request returns 200 (or non-401/403)
F3. Secret found as plaintext URL query parameter
F4. Syntactically invalid Bearer token accepted (returns 200)
```

**F4 implementation requirements:**
- Only runs for MCPAdapter (requires HTTP POST to target)
- Only runs if F2 did NOT fire (F2 already covers the case of no-auth acceptance)
- Send HTTP POST with `Authorization: Bearer fynor.reliability.checker.invalid.token.v1`
- If response is HTTP 200 → failure F4 (token validation not enforced)
- If response is 401 or 403 → F4 passes (token correctly rejected)
- Network errors on F4 sub-check are silently skipped (not a failure)
- Secret token string is a constant, never a real token, never logged as a value

**Scoring model (unchanged from original, 4 failures now possible):**
`0→100, 1→40, 2→10, ≥3→0`

---

## Adding a New Check

Adding a check beyond the current 11 requires:

1. A taxonomy entry in `docs/adr/ADR-03-check-taxonomy.md` — signal class,
   agent-specific failure mode, rejected alternatives
2. A threshold justification in `docs/adr/ADR-04-threshold-justification.md`
   — statistical basis for pass threshold and scoring bands
3. An entry in this file (check-implementation-contract.md)
4. Scoring weight allocation — requires an ADR-02 amendment (weights are locked)
5. Tests covering all scoring bands and edge cases

A PR introducing a new check without all five items will be rejected.
