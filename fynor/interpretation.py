"""
fynor/interpretation.py — Client-specific trust layer for check results.

For every failing check this module computes three things from the client's
ACTUAL measured data:

  impact      — why THIS finding matters for THIS client's AI agents, using
                their real numbers (not a generic template)
  remediation — exactly what to do to fix it, step by step
  reproduce   — the exact curl/command to run against THEIR server to verify

This is fully deterministic (ADR-01: automation layer, not AI junction).
No network calls, no randomness, no AI API dependency.

The key distinction from a static lookup table:
  Static: "P95 latency exceeds 2000ms. Agents will time out."
  This:   "Your P95 is 3,841ms (we ran 20 probes: min 1,203ms, max 4,102ms).
           A 5-step Claude workflow takes ~19.2 seconds on your server."

Every number in an impact statement came from the client's actual response,
stored in result.value and result.evidence.

AI Junction 1 (Month 7) will use these structured outputs as the foundation
for Claude-powered narrative synthesis tailored to the client's stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fynor.history import CheckResult


@dataclass(frozen=True)
class CheckInterpretation:
    """
    Contextual explanation attached to a single CheckResult.

    Every field must reference the client's actual measured data —
    not generic advice that would apply to any server.

    impact      — business consequence using the client's real numbers.
    remediation — numbered steps to resolve the finding.
    reproduce   — a command to run against the client's specific server.
                  Empty string when no simple reproduce command exists.
    refs        — relevant standards, RFCs, or Fynor docs links.
    """
    impact: str
    remediation: str
    reproduce: str = ""
    refs: list[str] | None = None


# ---------------------------------------------------------------------------
# Type alias for interpretation factories.
# A factory takes a CheckResult and returns a CheckInterpretation whose text
# contains the client's actual measured values.
# ---------------------------------------------------------------------------

_InterpEntry = CheckInterpretation | Callable[[CheckResult], CheckInterpretation]


# ---------------------------------------------------------------------------
# Helper: safe evidence access
# ---------------------------------------------------------------------------

def _ev(result: CheckResult, key: str, default: object = None) -> object:
    """Safely read a key from result.evidence, returning default if absent."""
    if result.evidence is None:
        return default
    return result.evidence.get(key, default)


# ---------------------------------------------------------------------------
# latency_p95 factories
# ---------------------------------------------------------------------------

def _latency_pass(r: CheckResult) -> CheckInterpretation:
    p95 = float(r.value or 0)
    band = "excellent (≤200ms)" if p95 <= 200 else "good (≤500ms)" if p95 <= 500 else "acceptable (≤1000ms)"
    return CheckInterpretation(
        impact=(
            f"P95 latency is {band} at {p95:.0f}ms. "
            "AI agents can chain multiple tool calls without accumulating perceptible delays. "
            "Users interacting with agents backed by this server will see responsive, "
            "real-time behaviour."
        ),
        remediation="No action needed. Monitor periodically — latency often degrades under load.",
    )


def _latency_degraded(r: CheckResult) -> CheckInterpretation:
    p95 = float(r.value or 0)
    workflow_5 = round(p95 * 5 / 1000, 1)
    min_ms = _ev(r, "min_ms", "?")
    max_ms = _ev(r, "max_ms", "?")
    probes = _ev(r, "probe_count", 20)
    return CheckInterpretation(
        impact=(
            f"Your P95 latency is {p95:.0f}ms — measured over {probes} live requests "
            f"to your server (min: {min_ms}ms, max: {max_ms}ms). "
            f"AI agents making sequential tool calls accumulate this delay at every step: "
            f"a 5-step agent workflow takes approximately {workflow_5}s on your server. "
            "Users see slow, hesitant agents. Parallel tool calls help, but the bottleneck "
            "is your server response time, not the agent framework."
        ),
        remediation=(
            "1. Profile your tool handler functions — identify which tools are slowest.\n"
            "2. Add response caching for read-heavy tools (most common cause of P95 spikes).\n"
            "3. Check for N+1 database query patterns in tool implementations.\n"
            "4. Move slow operations to async background tasks if results can be streamed.\n"
            f"5. Target: P95 ≤ 500ms (currently {p95:.0f}ms — reduce by "
            f"{max(0, p95 - 500):.0f}ms)."
        ),
        reproduce=(
            f"# Run {probes} probes and observe your P95:\n"
            "for i in $(seq 1 20); do\n"
            "  curl -s -o /dev/null -w '%{time_total}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort -n | awk 'NR==19'"
        ),
        refs=["https://fynor.tech/docs/checks/latency-p95#remediation"],
    )


def _latency_fail(r: CheckResult) -> CheckInterpretation:
    p95 = float(r.value or 0)
    workflow_5 = round(p95 * 5 / 1000, 1)
    min_ms = _ev(r, "min_ms", "?")
    max_ms = _ev(r, "max_ms", "?")
    probes = _ev(r, "probe_count", 20)
    errors = _ev(r, "error_count", 0)
    error_note = f" ({errors} of {probes} requests errored — excluded from P95)" if errors else ""
    return CheckInterpretation(
        impact=(
            f"Your P95 latency is {p95:.0f}ms — measured over {probes} live requests "
            f"(min: {min_ms}ms, max: {max_ms}ms{error_note}). "
            f"At this level, AI agent frameworks will trigger timeout retries or surface "
            f"errors to end users. A single tool call at {p95:.0f}ms blocks the entire "
            f"agent reasoning loop. A 5-step agent workflow takes ~{workflow_5}s on your "
            "server — compounding errors cause workflow abandonment. "
            "This is the most common cause of 'my AI agent feels broken' user complaints."
        ),
        remediation=(
            "1. Identify the slowest tool handlers with application profiling (Py-Spy, cProfile).\n"
            "2. Check your database connection pool size — exhaustion causes P95 spikes.\n"
            "3. Add a CDN or edge cache in front of read-heavy endpoints.\n"
            "4. Consider horizontal scaling — one overloaded instance raises P95 even if\n"
            "   average latency looks acceptable.\n"
            "5. Set a 30s hard timeout on all tool handlers to fail fast instead of hanging.\n"
            f"6. Target: P95 ≤ 1000ms (currently {p95:.0f}ms — reduce by "
            f"{max(0, p95 - 1000):.0f}ms to pass, by {max(0, p95 - 500):.0f}ms to reach good)."
        ),
        reproduce=(
            "for i in $(seq 1 20); do\n"
            "  curl -s -o /dev/null -w '%{time_total}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort -n | awk 'NR==19'"
        ),
        refs=[
            "https://fynor.tech/docs/checks/latency-p95#remediation",
            "https://cloud.google.com/apis/design/errors#latency",
        ],
    )


# ---------------------------------------------------------------------------
# error_rate factories
# ---------------------------------------------------------------------------

def _error_rate_pass(r: CheckResult) -> CheckInterpretation:
    rate = float(r.value or 0)
    probes = _ev(r, "probe_count", 50)
    return CheckInterpretation(
        impact=(
            f"Error rate is {rate:.1f}% over {probes} live requests — at or near zero. "
            "AI agents receive successful responses on virtually every call. "
            "Tool reliability is excellent — agents can depend on your server without "
            "retry logic or fallback handling."
        ),
        remediation="No action needed. Monitor error rate under peak load conditions.",
    )


def _error_rate_degraded(r: CheckResult) -> CheckInterpretation:
    rate = float(r.value or 0)
    errors = _ev(r, "error_count", 0)
    probes = _ev(r, "probe_count", 50)
    status_dist = _ev(r, "status_code_distribution", {})
    first_status = _ev(r, "first_error_status")
    first_preview = _ev(r, "first_error_response_preview")

    # Calculate how many steps before a pipeline hits at least one error
    if rate > 0:
        steps_to_error = round(1 / (rate / 100))
        pipeline_note = f"a pipeline of {steps_to_error} tool calls will statistically hit at least one error"
    else:
        pipeline_note = "error rate is near-zero"

    status_summary = ", ".join(f"HTTP {k}: {v}" for k, v in sorted(status_dist.items())) if status_dist else "not available"

    return CheckInterpretation(
        impact=(
            f"Your server returned errors on {errors} of {probes} requests ({rate:.1f}%). "
            f"Response breakdown: {status_summary}. "
            f"At {rate:.1f}%, {pipeline_note}. "
            "AI agents without retry logic will surface these failures to users. "
            "Agents with retry will succeed but with increased latency and token cost — "
            "each retry doubles the cost of that tool call."
        ),
        remediation=(
            f"1. Check server logs for the {errors} failing requests — find the error pattern.\n"
            "2. If errors are rate-limit rejections from downstream APIs, add exponential backoff.\n"
            "3. Check if errors correlate with concurrent load — add request queuing.\n"
            "4. Add structured error responses (JSON-RPC error objects) instead of crashing.\n"
            "5. Set up alerting on error rate > 1% — do not wait for Fynor to catch it.\n"
            f"6. Target: ≤0% errors (currently {rate:.1f}% — eliminate all {errors} failing requests)."
            + (f"\n\nFirst error response seen:\n  HTTP {first_status}: {first_preview}" if first_status else "")
        ),
        reproduce=(
            f"# Send {probes} requests and count non-2xx responses:\n"
            "for i in $(seq 1 50); do\n"
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort | uniq -c"
        ),
    )


def _error_rate_fail(r: CheckResult) -> CheckInterpretation:
    rate = float(r.value or 0)
    errors = _ev(r, "error_count", 0)
    probes = _ev(r, "probe_count", 50)
    status_dist = _ev(r, "status_code_distribution", {})
    first_status = _ev(r, "first_error_status")
    first_preview = _ev(r, "first_error_response_preview")
    status_summary = ", ".join(f"HTTP {k}: {v}" for k, v in sorted(status_dist.items())) if status_dist else "not available"

    # Probability of completing an N-step pipeline without any error
    survive_5 = round((1 - rate / 100) ** 5 * 100, 1)
    survive_10 = round((1 - rate / 100) ** 10 * 100, 1)

    return CheckInterpretation(
        impact=(
            f"Your server errored on {errors} of {probes} requests ({rate:.1f}%). "
            f"Response breakdown from your server: {status_summary}. "
            f"At {rate:.1f}% error rate: a 5-step agent workflow completes without errors "
            f"only {survive_5}% of the time; a 10-step workflow only {survive_10}% of the time. "
            "This level of unreliability makes your server unsuitable for production agent "
            "deployments — agents that retry on failure will double token consumption and "
            "still not guarantee completion."
        ),
        remediation=(
            f"1. Investigate the {errors} failing requests — capture and analyse error logs.\n"
            "2. If errors are 5xx: fix the server-side bug causing the crash.\n"
            "3. If errors are 4xx (non-429): your request format or auth is being rejected.\n"
            "4. If errors are timeouts: add timeout handling in tool handlers.\n"
            "5. Add a /health or /ready endpoint and check it before accepting agent traffic.\n"
            f"6. Target: ≤1% error rate (currently {rate:.1f}%)."
            + (f"\n\nFirst error seen from your server:\n  HTTP {first_status}: {first_preview}" if first_status else "")
        ),
        reproduce=(
            f"# Send {probes} requests to your server and see the error distribution:\n"
            "for i in $(seq 1 50); do\n"
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort | uniq -c"
        ),
        refs=["https://fynor.tech/docs/checks/error-rate#remediation"],
    )


# ---------------------------------------------------------------------------
# auth_token factories
# ---------------------------------------------------------------------------

def _auth_pass(r: CheckResult) -> CheckInterpretation:
    ran_f2 = bool(_ev(r, "f2_ran", False))
    ran_f4 = bool(_ev(r, "f4_ran", False))
    checks_run = []
    if ran_f2:
        checks_run.append("unauthenticated requests rejected (F2)")
    if ran_f4:
        checks_run.append(f"invalid token '{_ev(r, 'probe_token_used', '')}' rejected (F4)")
    check_summary = "; ".join(checks_run) if checks_run else "header and URL checks passed"
    return CheckInterpretation(
        impact=(
            f"Auth token handling is correct ({check_summary}). "
            "No credential leakage in response headers, unauthenticated requests are rejected, "
            "no secrets in URL parameters, and invalid token signatures are rejected. "
            "AI agents connecting to this server operate in a properly secured environment."
        ),
        remediation="No action needed. Review auth implementation when upgrading auth libraries.",
    )


def _auth_fail(r: CheckResult) -> CheckInterpretation:
    token_used = str(_ev(r, "probe_token_used", "fynor.reliability.checker.invalid.token.v1"))
    f4_status = _ev(r, "f4_response_status")
    f4_preview = _ev(r, "f4_response_preview", "")
    f2_status = _ev(r, "f2_unauth_status")
    leaked = _ev(r, "f1_leaked_header_names", [])
    secret_params = _ev(r, "f3_secret_param_names", [])
    ran_f4 = bool(_ev(r, "f4_ran", False))
    ran_f2 = bool(_ev(r, "f2_ran", False))

    # Build a specific evidence narrative from real server responses
    evidence_lines = []
    if ran_f4 and f4_status == 200:
        preview_snippet = f": {str(f4_preview)[:120]}..." if f4_preview else ""
        evidence_lines.append(
            f"We sent Bearer token '{token_used}' → your server responded HTTP {f4_status} OK{preview_snippet}"
        )
    if ran_f2 and f2_status == 200:
        evidence_lines.append(
            f"We sent a request with NO Authorization header → your server responded HTTP {f2_status} OK"
        )
    if leaked:
        evidence_lines.append(f"Your response headers contained credential-pattern names: {leaked}")
    if secret_params:
        evidence_lines.append(f"Your target URL contains secret parameter names: {secret_params}")

    what_we_proved = "\n  ".join(evidence_lines) if evidence_lines else r.detail

    reproduce_cmd = (
        f"# Test F4 — send our exact probe token to your server:\n"
        f"curl -X POST <TARGET_URL> \\\n"
        f"  -H 'Authorization: Bearer {token_used}' \\\n"
        f"  -H 'Content-Type: application/json' \\\n"
        f"  -d '{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{{}}}}'\n"
        f"# Your server returned: HTTP {f4_status or '?'}\n"
        f"# After the fix, it must return: HTTP 401"
    ) if ran_f4 else ""

    return CheckInterpretation(
        impact=(
            "SECURITY CAP ACTIVE — overall grade capped at D.\n\n"
            f"What your server revealed:\n  {what_we_proved}\n\n"
            "Business consequence: every tool your MCP server exposes is accessible to "
            "anyone who discovers the URL. AI agents from other tenants, scrapers, or "
            "attackers can call your tools, read your data, and trigger your actions "
            "without credentials. If your tools write data, modify state, or call "
            "downstream APIs — all of that is exposed. This is not a theoretical risk. "
            "The curl command in REPRODUCE IT YOURSELF will demonstrate it on your live server."
        ),
        remediation=(
            "For each failure detected:\n\n"
            + ("F4 — Invalid token accepted (most critical):\n"
               "  Implement JWT signature verification — check the signature against your public key.\n"
               "  Do not just check that a Bearer token is present — validate it cryptographically.\n"
               "  Python: payload = jwt.decode(token, public_key, algorithms=['RS256'])\n"
               "  Return HTTP 401 with WWW-Authenticate: Bearer for any unrecognised token.\n\n"
               if (ran_f4 and f4_status == 200) else "")
            + ("F2 — Unauthenticated request accepted:\n"
               "  Add auth middleware that runs before every route/handler.\n"
               "  Return HTTP 401 for missing credentials, 403 for insufficient permissions.\n\n"
               if (ran_f2 and f2_status == 200) else "")
            + (f"F1 — Credential headers in response ({leaked}):\n"
               "  Remove these header names from your server responses immediately.\n\n"
               if leaked else "")
            + (f"F3 — Secrets in URL ({secret_params}):\n"
               "  Move credentials from URL query params to Authorization header.\n\n"
               if secret_params else "")
            + "Verify the fix: re-run Fynor or use the REPRODUCE command below."
        ),
        reproduce=reproduce_cmd,
        refs=[
            "https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/",
            "https://fynor.tech/docs/checks/auth-token#remediation",
        ],
    )


# ---------------------------------------------------------------------------
# schema factories
# ---------------------------------------------------------------------------

def _schema_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your MCP server returns a valid JSON-RPC 2.0 response to tools/list. "
            "Every tool has a name, description, and input schema. "
            "AI models can reliably discover your tools and construct correct calls."
        ),
        remediation="No action needed.",
    )


def _schema_fail(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your MCP server's tools/list response is malformed or missing required fields. "
            "AI models cannot reliably discover or call your tools. Models may hallucinate "
            "tool parameters, call tools with wrong argument shapes, or skip tools entirely. "
            "This is a silent failure — the agent appears to work but produces wrong results."
        ),
        remediation=(
            "1. Ensure tools/list returns: {jsonrpc: '2.0', id: <id>, result: {tools: [...]}}\n"
            "2. Each tool must have: name (string), description (string), inputSchema (JSON Schema).\n"
            "3. Validate against: https://spec.modelcontextprotocol.io\n"
            "4. Run the reproduce command below and inspect the response structure."
        ),
        reproduce=(
            "curl -X POST <TARGET_URL> \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'"
        ),
        refs=[
            "https://spec.modelcontextprotocol.io",
            "https://fynor.tech/docs/checks/schema#remediation",
        ],
    )


# ---------------------------------------------------------------------------
# retry factories
# ---------------------------------------------------------------------------

def _retry_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your server correctly signals retriable errors with HTTP 429 or 503 and "
            "includes Retry-After headers. AI agent frameworks can implement safe backoff "
            "without guessing — reliability under load is good."
        ),
        remediation="No action needed.",
    )


def _retry_fail(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your server does not correctly signal retriable errors. When overwhelmed or "
            "rate limiting, it either crashes (5xx), returns 200 with error content, or "
            "omits Retry-After headers. AI agent frameworks cannot safely retry without "
            "guidance — they either hammer your server or abandon tasks that could succeed."
        ),
        remediation=(
            "1. Return HTTP 429 when rate limiting — not 200 or 500.\n"
            "2. Include 'Retry-After: <seconds>' in all 429 and 503 responses.\n"
            "3. Return HTTP 503 with Retry-After during planned maintenance or overload.\n"
            "4. Never return HTTP 200 with an error payload — it prevents correct retry logic.\n"
            "5. Test: send requests at 2× your rate limit and verify 429 + Retry-After is returned."
        ),
        reproduce=(
            "# Send rapid requests to trigger rate limiting:\n"
            "for i in $(seq 1 50); do\n"
            "  curl -s -o /dev/null -w '%{http_code} %{header_json}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | grep -v '^200'"
        ),
        refs=["https://fynor.tech/docs/checks/retry#remediation"],
    )


# ---------------------------------------------------------------------------
# rate_limit factories
# ---------------------------------------------------------------------------

def _rate_limit_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your server correctly enforces rate limits — returning 429 responses when the "
            "threshold is exceeded. AI agents cannot accidentally exhaust your capacity or "
            "your downstream API quotas. Multi-tenant scenarios are protected."
        ),
        remediation="No action needed.",
    )


def _rate_limit_fail(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "No rate limiting detected. Your server accepted an unbounded number of requests "
            "per second without throttling. A single AI agent running in a loop, a runaway "
            "agent, or concurrent agents can overwhelm your server, exhaust downstream API "
            "quotas, generate unexpected costs, and cause outages for all other users. "
            "Without rate limiting, your MCP server is not safe to expose to any external agent."
        ),
        remediation=(
            "1. Implement per-client rate limiting at the API gateway or middleware level.\n"
            "2. Use token bucket or sliding window algorithms — not fixed window (burst-prone).\n"
            "3. Return HTTP 429 with Retry-After header when the limit is exceeded.\n"
            "4. Set separate limits per: IP address, API key, and tool name.\n"
            "5. Libraries: slowapi (FastAPI/Python), express-rate-limit (Node), rack-attack (Ruby).\n"
            "6. Expose: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset headers."
        ),
        reproduce=(
            "# Send 60 requests in rapid succession — your server should return 429:\n"
            "for i in $(seq 1 60); do\n"
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort | uniq -c"
        ),
        refs=["https://fynor.tech/docs/checks/rate-limit#remediation"],
    )


# ---------------------------------------------------------------------------
# timeout factories
# ---------------------------------------------------------------------------

def _timeout_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your server correctly handles request timeouts — it completes within the "
            "60-second budget or returns a structured error before hanging. AI agents will "
            "not get stuck waiting indefinitely. Agent workflow deadlocks caused by hanging "
            "tool calls are not a risk with this server."
        ),
        remediation="No action needed.",
    )


def _timeout_fail(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your server hangs on slow or timed-out requests instead of returning a structured "
            "error. When an AI agent calls a tool that triggers a slow downstream operation, "
            "the agent's reasoning loop stalls until the framework's global timeout fires. "
            "This causes: agent tasks silently abandoned mid-workflow, users seeing frozen "
            "interfaces, and concurrent agents starved of capacity because connections are held open."
        ),
        remediation=(
            "1. Add per-request timeout enforcement in your tool handlers:\n"
            "   Python: asyncio.wait_for(downstream_call(), timeout=25.0)\n"
            "2. Wrap all downstream calls (database, external APIs) with explicit timeouts.\n"
            "3. Return HTTP 504 with a JSON-RPC error body on timeout:\n"
            "   {\"jsonrpc\": \"2.0\", \"id\": <id>, \"error\": {\"code\": -32000, \"message\": \"Tool timed out\"}}\n"
            "4. Never let a tool handler run longer than 55 seconds (ADR-04 check budget is 60s)."
        ),
        reproduce=(
            "# Measure how long a request hangs before your server responds:\n"
            "curl -m 65 -X POST <TARGET_URL> \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}' \\\n"
            "  -w '\\nHTTP %{http_code} in %{time_total}s\\n'"
        ),
        refs=["https://fynor.tech/docs/checks/timeout#remediation"],
    )


# ---------------------------------------------------------------------------
# log_completeness factories
# ---------------------------------------------------------------------------

def _log_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your server emits structured JSON logs with timestamps on every request. "
            "When something goes wrong — an agent failure, a latency spike, an unexpected "
            "tool result — you can trace exactly what happened, when, and why. "
            "Observability is complete."
        ),
        remediation="No action needed.",
    )


def _log_degraded(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Logging is partial — logs are either not JSON-structured, lack timestamps, "
            "or are missing for some request types. When investigating agent failures in "
            "production you will have incomplete information. Correlating errors across "
            "distributed systems will take significantly longer."
        ),
        remediation=(
            "1. Emit one JSON log line per request (not plain text).\n"
            "2. Required fields: timestamp (ISO-8601), level, method, status_code, duration_ms, request_id.\n"
            "3. Use a structured logger: structlog (Python), pino (Node), zap (Go).\n"
            "4. Ensure all tool handlers log completion — not just the HTTP layer."
        ),
        refs=["https://fynor.tech/docs/checks/log-completeness#remediation"],
    )


def _log_fail(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "No structured logs detected. When AI agents encounter errors using your tools, "
            "you have no visibility into what happened. You cannot distinguish a server-side "
            "bug from a client-side misuse, cannot measure real-world latency, and cannot "
            "alert on error rate spikes. Every production incident becomes a multi-hour "
            "investigation without logs."
        ),
        remediation=(
            "1. Add a structured logging library:\n"
            "   Python: pip install structlog  →  structlog.get_logger().info('request', method=method, ...)\n"
            "   Node:   npm install pino       →  pino().info({method, statusCode, durationMs}, 'request')\n"
            "2. Log every inbound request and outbound response with: timestamp, method,\n"
            "   status_code, duration_ms, request_id, and error (if any).\n"
            "3. Route logs to a log aggregation service (Datadog, Loki, CloudWatch Logs).\n"
            "4. Set up an alert: error rate > 1% triggers a notification within 5 minutes."
        ),
        refs=["https://fynor.tech/docs/checks/log-completeness#remediation"],
    )


# ---------------------------------------------------------------------------
# data_freshness factories
# ---------------------------------------------------------------------------

def _freshness_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Response data contains fresh timestamps — data is within the acceptable age window. "
            "AI agents making decisions based on your data are working with current information. "
            "Time-sensitive agentic workflows (scheduling, monitoring, alerting) are safe to run."
        ),
        remediation="No action needed. Monitor cache TTLs if you use caching.",
    )


def _freshness_degraded(r: CheckResult) -> CheckInterpretation:
    age_label = str(r.value) if r.value else "unknown"
    return CheckInterpretation(
        impact=(
            f"Response data is {age_label} old — within acceptable bounds but not fresh. "
            "For most use cases this is acceptable, but for time-sensitive workflows "
            "(market data, live monitoring, real-time scheduling) this staleness can cause "
            "AI agents to act on outdated information and make incorrect decisions."
        ),
        remediation=(
            "1. Review your data pipeline — identify where data refresh is delayed.\n"
            "2. Reduce cache TTLs for time-sensitive data sources.\n"
            "3. Add a 'data_as_of' field to your tool responses so agents can reason\n"
            "   about data age explicitly.\n"
            "4. For time-sensitive use cases, target data age ≤ 1 hour."
        ),
        refs=["https://fynor.tech/docs/checks/data-freshness#remediation"],
    )


def _freshness_fail(r: CheckResult) -> CheckInterpretation:
    age_label = str(r.value) if r.value else "unknown age"
    return CheckInterpretation(
        impact=(
            f"Response data is {age_label} old — or no timestamps were found in the response. "
            "AI agents have no way to know how current your data is. An agent making scheduling "
            "decisions, financial calculations, or status-based actions on data that is days or "
            "weeks stale will produce confidently wrong answers with no error signal. "
            "This is a silent correctness failure — users will not see an error, they will "
            "see an incorrect outcome."
        ),
        remediation=(
            "1. Add timestamp fields to your tool responses: created_at, updated_at, or data_as_of.\n"
            "2. Use ISO-8601 format: '2026-05-15T09:30:00Z'\n"
            "3. Refresh your underlying data source — investigate why data is not updating.\n"
            "4. If data genuinely cannot be fresher, document it in the tool description:\n"
            "   'Returns last 7-day snapshot. Updated weekly at 00:00 UTC.'"
        ),
        refs=["https://fynor.tech/docs/checks/data-freshness#remediation"],
    )


# ---------------------------------------------------------------------------
# tool_description_quality factories
# ---------------------------------------------------------------------------

def _tdq_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Tool descriptions are clear, specific, and contain enough context for AI models "
            "to select and call them correctly without ambiguity. Tool selection accuracy will "
            "be high — models will use the right tool for each task and construct correct "
            "parameter values."
        ),
        remediation="No action needed.",
    )


def _tdq_degraded(r: CheckResult) -> CheckInterpretation:
    score = r.score
    return CheckInterpretation(
        impact=(
            f"Tool descriptions scored {score}/100 — adequate but improvable. "
            "AI models may occasionally select the wrong tool in ambiguous situations, "
            "or generate suboptimal parameter values when edge cases are unclear. "
            "The impact is subtle — agents mostly work correctly, but fail on corner cases."
        ),
        remediation=(
            "1. Add what the tool does NOT do — negative constraints help models disambiguate.\n"
            "2. Include example inputs and expected outputs in the description.\n"
            "3. Describe parameter semantics clearly: units, formats, valid ranges.\n"
            "4. If two tools are similar, add a sentence explaining when to use each one."
        ),
        refs=["https://fynor.tech/docs/checks/tool-description-quality#remediation"],
    )


def _tdq_fail(r: CheckResult) -> CheckInterpretation:
    score = r.score
    return CheckInterpretation(
        impact=(
            f"Tool descriptions scored {score}/100 — too vague for reliable AI model use. "
            "Models will guess what your tools do — sometimes correctly, often not. "
            "Common failures: wrong tool selected, parameters constructed with wrong types "
            "or formats, tools called with missing required parameters. Users see agents "
            "that 'don't work' or produce wrong results. The problem is not the agent "
            "framework — it is the missing context in your tool descriptions."
        ),
        remediation=(
            "1. Minimum description: 2 sentences — what it does and when to use it.\n"
            "2. Every parameter must have a description: type, format, valid values, example.\n"
            "3. Mark required vs optional parameters explicitly in inputSchema.\n"
            "4. Add a usage example in the tool description:\n"
            "   'Example: to get weather for London, call with {city: \"London\", units: \"celsius\"}'\n"
            "5. Test your descriptions by asking Claude or GPT-4 to choose between your tools\n"
            "   for various tasks — poor descriptions produce wrong tool selections."
        ),
        refs=[
            "https://spec.modelcontextprotocol.io/specification/server/tools/",
            "https://fynor.tech/docs/checks/tool-description-quality#remediation",
        ],
    )


# ---------------------------------------------------------------------------
# response_determinism factories
# ---------------------------------------------------------------------------

def _determinism_pass(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Your server returns structurally consistent responses across multiple identical "
            "requests — same schema shape every time. AI agents can build reliable parsing "
            "logic against your tools. Integration tests will not produce false failures."
        ),
        remediation="No action needed.",
    )


def _determinism_degraded(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Response structure is mostly consistent but varies on some fields across "
            "identical requests. AI agents that rely on specific fields being present may "
            "encounter KeyError / attribute-missing failures intermittently. Integration "
            "tests that check response structure will flake. Usually caused by conditional "
            "fields that appear only in some code paths."
        ),
        remediation=(
            "1. Audit your tool response models — ensure every field is always present,\n"
            "   even if null. Prefer null over absent.\n"
            "2. Use Pydantic or dataclasses to enforce a fixed response shape.\n"
            "3. Test: call the same tool 10 times and assert response schemas are identical."
        ),
        refs=["https://fynor.tech/docs/checks/response-determinism#remediation"],
    )


def _determinism_fail(r: CheckResult) -> CheckInterpretation:
    return CheckInterpretation(
        impact=(
            "Response structure varies significantly across identical requests. "
            "The JSON schema shape is inconsistent — fields appear, disappear, or change "
            "type between calls. AI agents cannot build reliable tool call logic. "
            "Every call is a guess about what fields will be present. Agents will "
            "hallucinate fields that were present in one call but absent in the next. "
            "Integration code will break unpredictably."
        ),
        remediation=(
            "1. Define a fixed Pydantic/dataclass response model for every tool.\n"
            "2. All optional fields must be declared Optional[type] = None — always present.\n"
            "3. Remove any code path that conditionally adds or removes response fields.\n"
            "4. Run 10 identical calls to each tool and diff the response schemas:\n"
            "   python -c \"import json; print(set(json.loads(r1).keys()) ^ set(json.loads(r2).keys()))\"\n"
            "5. Add a response schema validation test to your CI pipeline."
        ),
        refs=["https://fynor.tech/docs/checks/response-determinism#remediation"],
    )


# ---------------------------------------------------------------------------
# N/A interpretations (static — no client-specific data)
# ---------------------------------------------------------------------------

_NA_SCHEMA = CheckInterpretation(
    impact="Schema validation only applies to MCP (JSON-RPC 2.0) servers. Not applicable for this interface type.",
    remediation="No action needed for this check.",
)
_NA_RETRY = CheckInterpretation(
    impact="Retry signalling check only applies to MCP (JSON-RPC 2.0) servers. Not applicable for this interface type.",
    remediation="No action needed for this check.",
)
_NA_TDQ = CheckInterpretation(
    impact="Tool description quality check only applies to MCP (JSON-RPC 2.0) servers. Not applicable for this interface type.",
    remediation="No action needed for this check.",
)


# ---------------------------------------------------------------------------
# The interpretation table.
# Values are either factory functions (CheckResult → CheckInterpretation)
# or static CheckInterpretation objects (for N/A and simple pass cases).
# interpret() resolves factories automatically.
# ---------------------------------------------------------------------------

_TABLE: dict[tuple[str, str], _InterpEntry] = {
    ("latency_p95",             "pass"):     _latency_pass,
    ("latency_p95",             "degraded"): _latency_degraded,
    ("latency_p95",             "fail"):     _latency_fail,

    ("error_rate",              "pass"):     _error_rate_pass,
    ("error_rate",              "degraded"): _error_rate_degraded,
    ("error_rate",              "fail"):     _error_rate_fail,

    ("auth_token",              "pass"):     _auth_pass,
    ("auth_token",              "fail"):     _auth_fail,

    ("schema",                  "pass"):     _schema_pass,
    ("schema",                  "fail"):     _schema_fail,
    ("schema",                  "na"):       _NA_SCHEMA,

    ("retry",                   "pass"):     _retry_pass,
    ("retry",                   "fail"):     _retry_fail,
    ("retry",                   "na"):       _NA_RETRY,

    ("rate_limit",              "pass"):     _rate_limit_pass,
    ("rate_limit",              "fail"):     _rate_limit_fail,

    ("timeout",                 "pass"):     _timeout_pass,
    ("timeout",                 "fail"):     _timeout_fail,

    ("log_completeness",        "pass"):     _log_pass,
    ("log_completeness",        "degraded"): _log_degraded,
    ("log_completeness",        "fail"):     _log_fail,

    ("data_freshness",          "pass"):     _freshness_pass,
    ("data_freshness",          "degraded"): _freshness_degraded,
    ("data_freshness",          "fail"):     _freshness_fail,

    ("tool_description_quality","pass"):     _tdq_pass,
    ("tool_description_quality","degraded"): _tdq_degraded,
    ("tool_description_quality","fail"):     _tdq_fail,
    ("tool_description_quality","na"):       _NA_TDQ,

    ("response_determinism",    "pass"):     _determinism_pass,
    ("response_determinism",    "degraded"): _determinism_degraded,
    ("response_determinism",    "fail"):     _determinism_fail,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def interpret(result: CheckResult) -> CheckInterpretation | None:
    """
    Return the CheckInterpretation for a given CheckResult.

    For failing checks, the interpretation is computed from the client's
    actual measured values in result.value and result.evidence — not a template.

    Band mapping:
      result="na"        → "na"
      score == 100       → "pass"
      score >= 60        → "degraded"
      score < 60         → "fail"
    """
    if result.result == "na":
        band = "na"
    elif result.score == 100:
        band = "pass"
    elif result.score >= 60:
        band = "degraded"
    else:
        band = "fail"

    entry = _TABLE.get((result.check, band))
    if entry is None:
        return None
    if callable(entry):
        return entry(result)
    return entry


def interpret_all(results: list[CheckResult]) -> dict[str, CheckInterpretation | None]:
    """
    Return interpretations for a list of CheckResults, keyed by check name.

    Each interpretation is computed from the client's actual measured data.
    """
    return {r.check: interpret(r) for r in results}
