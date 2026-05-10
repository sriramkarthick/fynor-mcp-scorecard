# Complete Checks Catalog — All 40 Checks

## Failure Code Format
{TYPE}_{###}_{DESCRIPTOR}
Example: MCP_001_HIGH_LATENCY

## Severity Levels
CRITICAL — blocks agent operation entirely; hard cap at grade D
HIGH     — causes agent data corruption or auth failure
MEDIUM   — degrades agent reliability significantly
LOW      — minor inefficiency; agent still functions

## Score Buckets
Security    (30% of total score): all SEC checks + MCP_005 + MCP_006 + SOAP_003
Reliability (40% of total score): error rate, retry, timeout, auth, schema, log checks
Performance (30% of total score): response time, rate limit, pagination, throughput checks

## Agent-Specific Failure Mode Principle
Every check detects failures that HUMANS can recover from but AGENTS cannot.
Humans read error messages. Agents pipeline them.
Humans retry manually. Agents halt on unexpected responses.
Humans notice slow UI. Agents accumulate latency across 50-step chains.

---

## MCP Checks — 8 checks (v0.1, Month 6 — BUILD FIRST)

| Code    | Name                 | Failure Code                    | Bucket      | Severity |
|---------|----------------------|---------------------------------|-------------|----------|
| MCP_001 | Response Time P95    | MCP_001_HIGH_LATENCY            | Performance | MEDIUM   |
| MCP_002 | Error Rate 24h       | MCP_002_HIGH_ERROR_RATE         | Reliability | HIGH     |
| MCP_003 | Schema Validation    | MCP_003_SCHEMA_DRIFT            | Reliability | HIGH     |
| MCP_004 | Retry Behavior       | MCP_004_NO_RETRY_ON_TRANSIENT   | Reliability | HIGH     |
| MCP_005 | Auth Token Handling  | MCP_005_AUTH_TOKEN_LEAKED       | Security    | CRITICAL |
| MCP_006 | Rate Limit Compliance| MCP_006_RATE_LIMIT_ABSENT       | Security    | HIGH     |
| MCP_007 | Timeout Handling     | MCP_007_TIMEOUT_HANG            | Reliability | MEDIUM   |
| MCP_008 | Log Completeness     | MCP_008_LOG_INCOMPLETE          | Reliability | LOW      |

Agent failure modes:
MCP_001: P95 >2000ms — latency accumulates across 50-step agent chains, pipeline stalls
MCP_002: >5% non-2xx over 24h — silent failure patterns; agent treats errors as progress
MCP_003: response fields don't match MCP spec — agent downstream parser breaks silently
MCP_004: crash on malformed input — one transient failure aborts entire agent pipeline
MCP_005: token in response headers — agents log ALL headers; leaked keys persist in logs forever
MCP_006: no 429 on 100 req/sec burst — agent floods endpoint, triggering blanket bans
MCP_007: no graceful error on connection kill at 5s — agent hangs, entire pipeline blocks
MCP_008: no /logs or unstructured logs — missing audit trail breaks compliance requirements

How each check works mechanically:
MCP_001: 20 sequential HTTP requests -> compute 95th percentile latency
MCP_002: 50 requests over 5 minutes -> count non-2xx responses
MCP_003: compare response fields to published MCP spec (JSON Schema)
MCP_004: send malformed request -> check if server returns 400 vs. crashes
MCP_005: scan response headers for tokens; scan request config for hardcoded keys
MCP_006: send 100 requests/second burst -> verify 429 + backoff headers
MCP_007: send request, kill connection at 5s -> check graceful error vs. hang
MCP_008: check if server exposes /logs endpoint with timestamp + structured format

---

## REST Checks — 6 checks (v0.2, Month 9)

| Code     | Name                    | Failure Code                    | Bucket      | Severity |
|----------|-------------------------|---------------------------------|-------------|----------|
| REST_001 | Schema Stability        | REST_001_SCHEMA_UNSTABLE        | Reliability | HIGH     |
| REST_002 | Burst Rate Limit        | REST_002_NO_BURST_RATE_LIMIT    | Security    | HIGH     |
| REST_003 | Pagination Complete     | REST_003_PAGINATION_BROKEN      | Reliability | MEDIUM   |
| REST_004 | Idempotency             | REST_004_NON_IDEMPOTENT_POST    | Reliability | CRITICAL |
| REST_005 | Error Readability       | REST_005_ERROR_UNREADABLE       | Reliability | HIGH     |
| REST_006 | Auth Token Expiry       | REST_006_AUTH_EXPIRY_SILENT     | Reliability | CRITICAL |

Agent failure modes:
REST_001: field names/types change without version bump -> agent parser breaks silently
REST_002: no 429 at machine-speed call rates -> agent floods endpoint undetected
REST_003: cursor/offset not returned on large result sets -> agent treats truncated data as complete
REST_004: non-idempotent POST called twice on retry -> duplicate transactions, double charges
REST_005: error body is HTML or unstructured string -> agent cannot parse; entire pipeline halts
REST_006: 401 returned mid-session with no refresh signal -> all subsequent calls fail silently

---

## Security Checks — 6 checks (v0.2, cross-cutting ALL interface types)

| Code    | Name                    | Failure Code                    | Severity |
|---------|-------------------------|---------------------------------|----------|
| SEC_001 | Credential in Headers   | SEC_001_CREDENTIAL_IN_HEADERS   | CRITICAL |
| SEC_002 | Secret in URL           | SEC_002_SECRET_IN_URL           | CRITICAL |
| SEC_003 | No TLS Enforcement      | SEC_003_NO_TLS                  | HIGH     |
| SEC_004 | Overpermissioned Scope  | SEC_004_OVERPERMISSIONED        | HIGH     |
| SEC_005 | PII in Error Response   | SEC_005_PII_IN_ERROR            | HIGH     |
| SEC_006 | CORS Wildcard           | SEC_006_CORS_WILDCARD           | MEDIUM   |

Agent failure modes:
SEC_001: API keys in X-Auth-Token or similar -> agents log all headers; keys persist in logs
SEC_002: API keys in URL query params -> agents embed configs in calls; visible in network traces
SEC_003: HTTP without HTTPS redirect -> agents don't warn about protocol; data sent in plaintext
SEC_004: write scope when read sufficient -> compromised agent token has write blast radius
SEC_005: stack traces or user data in 4xx/5xx bodies -> agents surface errors upstream; PII in logs
SEC_006: wildcard CORS on authenticated endpoints -> agent-accessible endpoints exposed cross-origin

Note: SEC checks run on ALL interface types (MCP, REST, GraphQL, gRPC, WebSocket, SOAP, CLI).
CRITICAL severity on any SEC check -> hard cap at grade D for the entire audit.

---

## GraphQL Checks — 4 checks (v0.3, Month 12)

| Code    | Name                    | Failure Code                    | Bucket      | Severity |
|---------|-------------------------|---------------------------------|-------------|----------|
| GQL_001 | Schema Drift            | GQL_001_SCHEMA_DRIFT            | Reliability | HIGH     |
| GQL_002 | No Depth Limit          | GQL_002_NO_DEPTH_LIMIT          | Security    | MEDIUM   |
| GQL_003 | N+1 Resolver            | GQL_003_N_PLUS_ONE              | Performance | MEDIUM   |
| GQL_004 | Subscription Silent     | GQL_004_SUBSCRIPTION_SILENT     | Reliability | HIGH     |

Agent failure modes:
GQL_001: introspection doesn't reflect actual schema -> agent builds query from stale schema; fails
GQL_002: no depth limit on nested queries -> agent generates deeply nested query; server crashes
GQL_003: unbatched resolvers on list fields -> agent iterates list; N DB calls per item; meltdown
GQL_004: WebSocket subscription silently dies -> agent loses real-time stream; acts on stale data

---

## WebSocket Checks — 4 checks (v0.3, Month 12)

| Code    | Name                    | Failure Code                    | Bucket      | Severity |
|---------|-------------------------|---------------------------------|-------------|----------|
| WSS_001 | No Reconnect            | WSS_001_NO_RECONNECT            | Reliability | HIGH     |
| WSS_002 | No Heartbeat            | WSS_002_NO_HEARTBEAT            | Reliability | MEDIUM   |
| WSS_003 | Order Not Guaranteed    | WSS_003_ORDER_NOT_GUARANTEED    | Reliability | HIGH     |
| WSS_004 | No Backpressure         | WSS_004_NO_BACKPRESSURE         | Performance | MEDIUM   |

Agent failure modes:
WSS_001: no auto-reconnect after drop -> agent loses stream; never resubscribes; operates blind
WSS_002: no keepalive ping/pong -> idle agent connection silently drops after timeout
WSS_003: out-of-order delivery on high-throughput streams -> agent processes events in wrong sequence
WSS_004: no flow control on fast-producing stream -> agent input buffer overflows; messages dropped

---

## gRPC Checks — 4 checks (v0.4, Month 15)

| Code     | Name                    | Failure Code                       | Bucket      | Severity |
|----------|-------------------------|------------------------------------|-------------|----------|
| GRPC_001 | Proto Breaking Change   | GRPC_001_PROTO_BREAKING            | Reliability | CRITICAL |
| GRPC_002 | Stream Not Cancelled    | GRPC_002_STREAM_NOT_CANCELLED      | Performance | MEDIUM   |
| GRPC_003 | Deadline Not Forwarded  | GRPC_003_DEADLINE_NOT_FORWARDED    | Reliability | HIGH     |
| GRPC_004 | No Retry on Unavailable | GRPC_004_NO_RETRY_UNAVAILABLE      | Reliability | HIGH     |

Agent failure modes:
GRPC_001: breaking field removal/type change -> agent compiled against old proto; silent deserialization fail
GRPC_002: server-side stream not cleaned up on client cancel -> resource leak; server accumulates open streams
GRPC_003: deadline not forwarded through call chain -> upstream deadline expires; downstream calls continue
GRPC_004: no retry on UNAVAILABLE status code -> single transient failure causes agent pipeline abort

---

## SOAP Checks — 3 checks (v0.4, Month 15)

| Code     | Name                    | Failure Code                    | Bucket      | Severity |
|----------|-------------------------|---------------------------------|-------------|----------|
| SOAP_001 | WSDL Drift              | SOAP_001_WSDL_DRIFT             | Reliability | HIGH     |
| SOAP_002 | Fault Unreadable        | SOAP_002_FAULT_UNREADABLE       | Reliability | HIGH     |
| SOAP_003 | WS-Security Broken      | SOAP_003_WS_SECURITY_BROKEN     | Security    | CRITICAL |

Agent failure modes:
SOAP_001: WSDL doesn't match actual service -> agent generates XML from WSDL; server rejects envelope
SOAP_002: SOAP fault body is human-readable prose -> agent cannot parse fault; treats it as success
SOAP_003: security header format changed/expired -> agent sends outdated token; silent auth failure

---

## CLI Checks — 5 checks (v0.5, Month 18)

| Code    | Name                    | Failure Code                    | Bucket      | Severity |
|---------|-------------------------|---------------------------------|-------------|----------|
| CLI_001 | Exit Code Consistency   | CLI_001_EXIT_CODE_WRONG         | Reliability | CRITICAL |
| CLI_002 | Machine-Readable Output | CLI_002_NO_JSON_OUTPUT          | Reliability | HIGH     |
| CLI_003 | Deterministic Output    | CLI_003_NONDETERMINISTIC        | Reliability | MEDIUM   |
| CLI_004 | Stdin/Pipe Support      | CLI_004_NO_STDIN_SUPPORT        | Performance | LOW      |
| CLI_005 | Version Flag            | CLI_005_NO_VERSION_FLAG         | Reliability | LOW      |

Agent failure modes:
CLI_001: non-zero exit code not returned on failure -> agent treats failed command as success (exit 0 = OK)
CLI_002: no --json flag -> agent parses human-formatted text; breaks on any format change
CLI_003: non-deterministic output (timestamps, random IDs) -> agent diff comparison fails silently
CLI_004: CLI does not read from stdin -> agent cannot chain CLI tools in pipelines
CLI_005: no --version or non-semver output -> agent cannot detect version mismatch before invoking

---

## Check Count by Version
v0.1 (Month 6):  8 checks  (MCP)
v0.2 (Month 9):  20 checks (+6 REST, +6 Security)
v0.3 (Month 12): 28 checks (+4 GraphQL, +4 WebSocket)
v0.4 (Month 15): 35 checks (+4 gRPC, +3 SOAP)
v0.5 (Month 18): 40 checks (+5 CLI)
v1.0 (Month 20): 40 checks unified under one platform

## CRITICAL Failure Codes (immediate grade D cap)
MCP_005_AUTH_TOKEN_LEAKED
SEC_001_CREDENTIAL_IN_HEADERS
SEC_002_SECRET_IN_URL
REST_004_NON_IDEMPOTENT_POST
REST_006_AUTH_EXPIRY_SILENT
GRPC_001_PROTO_BREAKING
SOAP_003_WS_SECURITY_BROKEN
CLI_001_EXIT_CODE_WRONG
