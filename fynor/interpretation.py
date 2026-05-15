"""
fynor/interpretation.py — Deterministic trust layer for check results.

For every check and every score band this module returns three things:
  impact      — why this finding matters for AI agent operators, in plain English
  remediation — exactly what to do to fix it, step by step
  reproduce   — the curl/command the client can run themselves to verify

This is fully deterministic (ADR-01: automation layer, not AI junction).
No network calls, no randomness, no AI API dependency.

AI Junction 1 (Month 7) will use these as the structured foundation for
Claude-powered narrative synthesis tailored to the client's specific stack.
"""

from __future__ import annotations

from dataclasses import dataclass

from fynor.history import CheckResult


@dataclass(frozen=True)
class CheckInterpretation:
    """
    Contextual explanation attached to a single CheckResult.

    impact      — business consequence for AI agents using this interface.
    remediation — numbered steps to resolve the finding.
    reproduce   — a command the client can run to verify the finding themselves.
                  Empty string when no simple reproduce command exists.
    refs        — relevant standards, RFCs, or OWASP entries (display as links).
    """
    impact: str
    remediation: str
    reproduce: str = ""
    refs: list[str] | None = None


# ---------------------------------------------------------------------------
# Interpretation table — (check_name, score_band) → CheckInterpretation
#
# Score bands:
#   "pass"      score == 100  (everything is ideal)
#   "degraded"  score == 60 or 90  (partial pass — passes threshold but not perfect)
#   "fail"      score == 0  (threshold not met)
#   "na"        result == "na"  (not applicable for this interface type)
#
# For checks with intermediate bands (e.g. 40, 10) we map to "fail" —
# clients see the numeric score; we explain the failure class.
# ---------------------------------------------------------------------------

_TABLE: dict[tuple[str, str], CheckInterpretation] = {

    # ------------------------------------------------------------------ latency_p95
    ("latency_p95", "pass"): CheckInterpretation(
        impact=(
            "P95 latency is excellent (≤500ms). AI agents can chain multiple tool calls "
            "without accumulating perceptible delays. Users interacting with agents backed "
            "by this server will see responsive, real-time behaviour."
        ),
        remediation="No action needed. Monitor periodically — latency often degrades under load.",
        reproduce=(
            "# Run 20 probes and observe P95:\n"
            "for i in $(seq 1 20); do\n"
            "  curl -s -o /dev/null -w '%{time_total}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort -n | awk 'NR==19'"
        ),
    ),
    ("latency_p95", "degraded"): CheckInterpretation(
        impact=(
            "P95 latency is degraded (500ms–2000ms). AI agents making sequential tool calls "
            "accumulate this delay at every step. A 5-step agent workflow takes 2.5–10 seconds — "
            "users see slow, hesitant agents. Parallel tool calls help, but the bottleneck is "
            "your server's response time, not the agent framework."
        ),
        remediation=(
            "1. Profile your tool handler functions — identify which tools are slowest.\n"
            "2. Add response caching for read-heavy tools (most common cause of P95 spikes).\n"
            "3. Check for N+1 database query patterns in tool implementations.\n"
            "4. Move slow operations to async background tasks if results can be streamed.\n"
            "5. Target: P95 ≤ 500ms for excellent agent responsiveness."
        ),
        reproduce=(
            "for i in $(seq 1 20); do\n"
            "  curl -s -o /dev/null -w '%{time_total}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort -n | awk 'NR==19'"
        ),
        refs=["https://fynor.tech/docs/checks/latency-p95#remediation"],
    ),
    ("latency_p95", "fail"): CheckInterpretation(
        impact=(
            "P95 latency exceeds 2000ms. At this level, AI agent frameworks (LangChain, AutoGen, "
            "Claude tool use) will trigger timeout retries or surface errors to end users. A single "
            "slow tool call blocks the entire agent reasoning loop. Multi-step workflows become "
            "unreliable. Users abandon sessions. This is the most common cause of 'my AI agent "
            "feels broken' complaints from end users."
        ),
        remediation=(
            "1. Identify the slowest tool handlers with application profiling (Py-Spy, cProfile).\n"
            "2. Check your database connection pool size — pool exhaustion causes latency spikes.\n"
            "3. Add a CDN or edge cache in front of read-heavy endpoints.\n"
            "4. Consider horizontal scaling — one overloaded instance causes P95 spikes even if\n"
            "   average latency looks acceptable.\n"
            "5. Set a 30s hard timeout on all tool handlers to fail fast instead of hanging.\n"
            "6. Run load tests at 2× your expected agent concurrency to expose the bottleneck.\n"
            "Target: P95 ≤ 500ms. Do not ship latency above 2000ms to agent-facing production."
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
    ),

    # ------------------------------------------------------------------ error_rate
    ("error_rate", "pass"): CheckInterpretation(
        impact=(
            "Error rate is at or near zero. AI agents receive successful responses on virtually "
            "every call. Tool reliability is excellent — agents can depend on your server without "
            "retry logic or fallback handling."
        ),
        remediation="No action needed. Monitor error rate under peak load conditions.",
        reproduce=(
            "# Send 20 requests and count non-2xx responses:\n"
            "for i in $(seq 1 20); do\n"
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | grep -v '^2' | wc -l"
        ),
    ),
    ("error_rate", "degraded"): CheckInterpretation(
        impact=(
            "Error rate is 1–5%. AI agents encounter failed tool calls on roughly 1 in 20–100 "
            "requests. Agents without retry logic will surface these failures directly to users. "
            "Agents with retry will succeed but with increased latency and token cost. "
            "Complex multi-step workflows are statistically likely to hit at least one error."
        ),
        remediation=(
            "1. Check server logs for the most common error types (5xx vs 4xx).\n"
            "2. Look for resource exhaustion patterns — memory, file handles, DB connections.\n"
            "3. Add circuit breakers on downstream service calls inside your tools.\n"
            "4. Implement graceful degradation — return partial results rather than errors.\n"
            "5. Target: ≤0.1% error rate for production agent workloads."
        ),
        reproduce=(
            "for i in $(seq 1 20); do\n"
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | grep -v '^2' | wc -l"
        ),
    ),
    ("error_rate", "fail"): CheckInterpretation(
        impact=(
            "Error rate exceeds 5%. More than 1 in 20 tool calls fails. AI agents will surface "
            "these errors to users as tool failures, broken workflows, or silent incorrect results. "
            "Agentic systems that retry on failure will double their token consumption and still "
            "not guarantee completion. This level of unreliability makes your MCP server unsuitable "
            "for production agent deployments."
        ),
        remediation=(
            "1. Capture and analyse the failing request/response pairs — find the error pattern.\n"
            "2. Check if errors are rate-limit rejections from downstream APIs (add backoff).\n"
            "3. Check if errors correlate with concurrent load — add request queuing.\n"
            "4. Add structured error responses (JSON-RPC error objects) instead of crashing.\n"
            "5. Set up alerting on error rate > 1% — do not wait for Fynor to catch it.\n"
            "6. Do not deploy to agent-facing production above 1% error rate."
        ),
        reproduce=(
            "for i in $(seq 1 20); do\n"
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | grep -v '^2' | wc -l"
        ),
        refs=["https://fynor.tech/docs/checks/error-rate#remediation"],
    ),

    # ------------------------------------------------------------------ auth_token
    ("auth_token", "pass"): CheckInterpretation(
        impact=(
            "Auth token handling is correct across all sub-checks: no credential leakage in "
            "response headers, unauthenticated requests are rejected with 401/403, no secrets "
            "in URL parameters, and invalid token signatures are rejected. AI agents connecting "
            "to this server are operating in a properly secured environment."
        ),
        remediation="No action needed. Review auth implementation when upgrading auth libraries.",
        reproduce="",
    ),
    ("auth_token", "fail"): CheckInterpretation(
        impact=(
            "One or more authentication failures detected. Authentication is the only check with "
            "a grade cap: an auth score of 0 caps your overall Fynor grade at D regardless of "
            "all other scores. This reflects the severity: auth failures expose your MCP tools "
            "to unauthorized access, data exfiltration, billing fraud, and cross-tenant data "
            "leakage. AI agents operating in multi-tenant environments are especially at risk — "
            "one tenant's agent can call another tenant's tools."
        ),
        remediation=(
            "For each failure mode detected:\n\n"
            "F1 — Credential in response headers:\n"
            "  Remove any Authorization, X-Api-Key, X-Auth-Token, or similar headers\n"
            "  from your server responses. Response headers are not the right place for creds.\n\n"
            "F2 — Unauthenticated request accepted:\n"
            "  Add authentication middleware that runs before every tool handler.\n"
            "  Return HTTP 401 with 'WWW-Authenticate: Bearer' for missing credentials.\n"
            "  Return HTTP 403 for authenticated but unauthorized requests.\n\n"
            "F3 — Secret in URL parameters:\n"
            "  Remove api_key, token, secret from query parameters immediately.\n"
            "  URL params appear in server logs, CDN logs, browser history, and referrer headers.\n"
            "  Move credentials to Authorization header only.\n\n"
            "F4 — Invalid token accepted (signature not validated):\n"
            "  Implement JWT signature verification — check the token signature against\n"
            "  your public key, not just that a Bearer token is present.\n"
            "  Example (Python): jwt.decode(token, public_key, algorithms=['RS256'])\n"
            "  Test: the curl below must return 401 after the fix."
        ),
        reproduce=(
            "# Test F4 — invalid token acceptance:\n"
            "curl -X POST <TARGET_URL> \\\n"
            "  -H 'Authorization: Bearer fynor.reliability.checker.invalid.token.v1' \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "# Expected after fix: HTTP 401\n"
            "# Current result: HTTP 200 (failing)"
        ),
        refs=[
            "https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/",
            "https://fynor.tech/docs/checks/auth-token#remediation",
        ],
    ),

    # ------------------------------------------------------------------ schema
    ("schema", "pass"): CheckInterpretation(
        impact=(
            "Your MCP server returns a valid JSON-RPC 2.0 response to tools/list. Every tool "
            "has a name, description, and input schema. AI models can reliably discover your "
            "tools and construct correct calls — tool selection and parameter generation will work."
        ),
        remediation="No action needed.",
        reproduce="",
    ),
    ("schema", "fail"): CheckInterpretation(
        impact=(
            "Your MCP server's tools/list response is malformed or missing required fields. "
            "AI models cannot reliably discover or call your tools. Models may hallucinate "
            "tool parameters, call tools with wrong argument shapes, or skip tools entirely. "
            "This is a silent failure — the agent appears to work but produces wrong results."
        ),
        remediation=(
            "1. Ensure tools/list returns: {jsonrpc: '2.0', id: <id>, result: {tools: [...]}}\n"
            "2. Each tool must have: name (string), description (string), inputSchema (JSON Schema).\n"
            "3. Validate against the MCP specification: https://spec.modelcontextprotocol.io\n"
            "4. Run: curl -X POST <URL> -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "   and inspect the response structure."
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
    ),
    ("schema", "na"): CheckInterpretation(
        impact="Schema validation only applies to MCP (JSON-RPC 2.0) servers. Not applicable for this interface type.",
        remediation="No action needed for this check.",
    ),

    # ------------------------------------------------------------------ retry
    ("retry", "pass"): CheckInterpretation(
        impact=(
            "Your server correctly signals retriable errors with HTTP 429 (Too Many Requests) "
            "or HTTP 503 (Service Unavailable) and includes Retry-After headers. AI agent "
            "frameworks can implement safe backoff without guessing — reliability under load is good."
        ),
        remediation="No action needed.",
        reproduce="",
    ),
    ("retry", "fail"): CheckInterpretation(
        impact=(
            "Your server does not correctly signal retriable errors. When overwhelmed or rate "
            "limiting, it either crashes with 500, returns 200 with error content, or omits "
            "Retry-After headers. AI agent frameworks cannot safely retry without guidance — "
            "they either retry too aggressively (hammering your server) or give up immediately "
            "(abandoning tasks that could have succeeded). Under load, your server becomes less "
            "reliable, not just slower."
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
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done"
        ),
        refs=["https://fynor.tech/docs/checks/retry#remediation"],
    ),
    ("retry", "na"): CheckInterpretation(
        impact="Retry signalling check only applies to MCP (JSON-RPC 2.0) servers. Not applicable for this interface type.",
        remediation="No action needed for this check.",
    ),

    # ------------------------------------------------------------------ rate_limit
    ("rate_limit", "pass"): CheckInterpretation(
        impact=(
            "Your server correctly enforces rate limits — returning 429 responses when the "
            "request threshold is exceeded. AI agents cannot accidentally exhaust your capacity "
            "or your downstream API quotas. Multi-tenant scenarios are protected."
        ),
        remediation="No action needed.",
        reproduce="",
    ),
    ("rate_limit", "fail"): CheckInterpretation(
        impact=(
            "No rate limiting detected. Your server accepts an unbounded number of requests "
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
            "6. Expose your rate limit headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset."
        ),
        reproduce=(
            "# Send 60 requests in 10 seconds and verify 429 appears:\n"
            "for i in $(seq 1 60); do\n"
            "  curl -s -o /dev/null -w '%{http_code}\\n' -X POST <TARGET_URL> \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}'\n"
            "done | sort | uniq -c"
        ),
        refs=["https://fynor.tech/docs/checks/rate-limit#remediation"],
    ),

    # ------------------------------------------------------------------ timeout
    ("timeout", "pass"): CheckInterpretation(
        impact=(
            "Your server correctly handles request timeouts — it either completes within the "
            "budget or returns a structured error before hanging. AI agents will not get stuck "
            "waiting indefinitely for a response. Agent workflow deadlocks caused by hanging "
            "tool calls are not a risk with this server."
        ),
        remediation="No action needed.",
        reproduce="",
    ),
    ("timeout", "fail"): CheckInterpretation(
        impact=(
            "Your server hangs on slow or timed-out requests instead of returning a structured "
            "error. When an AI agent calls a tool that triggers a slow downstream operation, "
            "the agent's reasoning loop stalls until the framework's global timeout fires. "
            "This causes: agent tasks silently abandoned mid-workflow, users seeing frozen "
            "interfaces, and concurrent agents starved of capacity because connections are held open."
        ),
        remediation=(
            "1. Add per-request timeout enforcement in your tool handlers (not just at the "
            "   network level — middleware timeouts don't release application resources).\n"
            "2. Wrap all downstream calls (database, external APIs) with explicit timeouts:\n"
            "   Python: asyncio.wait_for(downstream_call(), timeout=25.0)\n"
            "3. Return HTTP 504 Gateway Timeout with a JSON-RPC error body on timeout:\n"
            "   {\"jsonrpc\": \"2.0\", \"id\": <id>, \"error\": {\"code\": -32000, \"message\": \"Tool timed out\"}}\n"
            "4. Never let a tool handler run longer than 55 seconds (leave buffer for the "
            "   60s check budget defined in ADR-04)."
        ),
        reproduce=(
            "# Test with a long-running request (requires a tool that accepts a delay param):\n"
            "curl -m 65 -X POST <TARGET_URL> \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"<slow_tool>\",\"params\":{}}' \\\n"
            "  -w '\\nHTTP %{http_code} in %{time_total}s\\n'"
        ),
        refs=["https://fynor.tech/docs/checks/timeout#remediation"],
    ),

    # ------------------------------------------------------------------ log_completeness
    ("log_completeness", "pass"): CheckInterpretation(
        impact=(
            "Your server emits structured JSON logs with timestamps on every request. "
            "When something goes wrong in production — an agent failure, a latency spike, "
            "an unexpected tool result — you can trace exactly what happened, when, and why. "
            "Observability is complete."
        ),
        remediation="No action needed.",
        reproduce="",
    ),
    ("log_completeness", "degraded"): CheckInterpretation(
        impact=(
            "Logging is partial — either logs are not JSON-structured, lack timestamps, or "
            "are missing for some request types. When investigating agent failures in production "
            "you will have incomplete information. Correlating errors across distributed systems "
            "or reproducing intermittent bugs will take significantly longer."
        ),
        remediation=(
            "1. Emit one JSON log line per request (not plain text).\n"
            "2. Required fields: timestamp (ISO-8601), level, method, status_code, duration_ms, request_id.\n"
            "3. Use a structured logger: structlog (Python), pino (Node), zap (Go).\n"
            "4. Ensure all tool handlers log completion — not just the HTTP layer."
        ),
        refs=["https://fynor.tech/docs/checks/log-completeness#remediation"],
    ),
    ("log_completeness", "fail"): CheckInterpretation(
        impact=(
            "No structured logs detected. When AI agents encounter errors using your tools, "
            "you have no visibility into what happened. You cannot distinguish a server-side "
            "bug from a client-side misuse, cannot measure real-world latency, and cannot "
            "alert on error rate spikes. Operating an agent-facing server without structured "
            "logs means every production incident becomes a multi-hour investigation."
        ),
        remediation=(
            "1. Add a structured logging library immediately:\n"
            "   Python: pip install structlog  →  structlog.get_logger().info('request', method=method, ...)\n"
            "   Node:   npm install pino       →  pino().info({method, statusCode, durationMs}, 'request')\n"
            "2. Log every inbound request and outbound response with: timestamp, method, "
            "   status_code, duration_ms, request_id, and error (if any).\n"
            "3. Route logs to a log aggregation service (Datadog, Loki, CloudWatch Logs).\n"
            "4. Set up an alert: error rate > 1% triggers a notification within 5 minutes."
        ),
        refs=["https://fynor.tech/docs/checks/log-completeness#remediation"],
    ),

    # ------------------------------------------------------------------ data_freshness
    ("data_freshness", "pass"): CheckInterpretation(
        impact=(
            "Response data contains fresh timestamps — data is less than 24 hours old. "
            "AI agents making decisions based on your data are working with current information. "
            "Time-sensitive agentic workflows (scheduling, monitoring, alerting) are safe to run."
        ),
        remediation="No action needed. Monitor cache TTLs if you use caching.",
        reproduce="",
    ),
    ("data_freshness", "degraded"): CheckInterpretation(
        impact=(
            "Response data timestamps indicate data is 24 hours to 7 days old. AI agents "
            "relying on your tools for current information may act on stale data. For most "
            "use cases this is acceptable, but for time-sensitive workflows (market data, "
            "live monitoring, real-time scheduling) this staleness can cause incorrect decisions."
        ),
        remediation=(
            "1. Review your data pipeline — identify where data refresh is delayed.\n"
            "2. Reduce cache TTLs for time-sensitive data sources.\n"
            "3. Add a 'data_as_of' field to your tool responses so agents can reason "
            "   about data age explicitly.\n"
            "4. For time-sensitive use cases, target data age ≤ 1 hour."
        ),
        refs=["https://fynor.tech/docs/checks/data-freshness#remediation"],
    ),
    ("data_freshness", "fail"): CheckInterpretation(
        impact=(
            "Response data is more than 7 days old, or no timestamps were found in the response. "
            "AI agents have no way to know how current the data is. An agent making scheduling "
            "decisions, financial calculations, or status-based actions on data that is days or "
            "weeks stale will produce confidently wrong answers. This is a silent correctness "
            "failure — users will not see an error, they will see an incorrect outcome."
        ),
        remediation=(
            "1. Add timestamp fields to your tool responses: created_at, updated_at, or data_as_of.\n"
            "2. Use ISO-8601 format: '2026-05-15T09:30:00Z'\n"
            "3. Refresh your underlying data source — investigate why data is not updating.\n"
            "4. If data genuinely cannot be fresher, document it in the tool's description "
            "   so agents can account for it: 'Returns last 7-day snapshot. Updated weekly.'"
        ),
        refs=["https://fynor.tech/docs/checks/data-freshness#remediation"],
    ),

    # ------------------------------------------------------------------ tool_description_quality
    ("tool_description_quality", "pass"): CheckInterpretation(
        impact=(
            "Tool descriptions are clear, specific, and contain enough context for AI models "
            "to select and call them correctly without ambiguity. Tool selection accuracy will "
            "be high — models will use the right tool for each task and construct correct "
            "parameter values."
        ),
        remediation="No action needed.",
        reproduce="",
    ),
    ("tool_description_quality", "degraded"): CheckInterpretation(
        impact=(
            "Tool descriptions are adequate but could be more specific. AI models may "
            "occasionally select the wrong tool in ambiguous situations, or generate "
            "suboptimal parameter values when the description doesn't clarify edge cases. "
            "The impact is subtle — agents mostly work correctly, but fail on corner cases."
        ),
        remediation=(
            "1. Add what the tool does NOT do — negative constraints help models disambiguate.\n"
            "2. Include example inputs and expected outputs in the description.\n"
            "3. Describe parameter semantics clearly: units, formats, valid ranges.\n"
            "4. If two tools are similar, add a sentence explaining when to use each one."
        ),
        refs=["https://fynor.tech/docs/checks/tool-description-quality#remediation"],
    ),
    ("tool_description_quality", "fail"): CheckInterpretation(
        impact=(
            "Tool descriptions are vague, missing, or too short for AI models to reliably "
            "understand what the tool does. Models will guess — sometimes correctly, often not. "
            "Common failures: wrong tool selected for a task, parameters constructed with "
            "wrong types or formats, tools called with missing required parameters. Users "
            "see agents that 'don't work' or produce wrong results. The problem is not the "
            "agent framework — it is the missing context in your tool descriptions."
        ),
        remediation=(
            "1. Minimum description: 2 sentences — what it does and when to use it.\n"
            "2. Every parameter must have a description: type, format, valid values, and an example.\n"
            "3. Mark required vs optional parameters explicitly in inputSchema.\n"
            "4. Add a usage example in the tool description:\n"
            "   'Example: to get weather for London, call with {city: \"London\", units: \"celsius\"}'\n"
            "5. Test your descriptions by asking Claude or GPT-4 to choose between your tools "
            "   for various tasks — poor descriptions produce wrong selections."
        ),
        refs=[
            "https://spec.modelcontextprotocol.io/specification/server/tools/",
            "https://fynor.tech/docs/checks/tool-description-quality#remediation",
        ],
    ),
    ("tool_description_quality", "na"): CheckInterpretation(
        impact="Tool description quality check only applies to MCP (JSON-RPC 2.0) servers. Not applicable for this interface type.",
        remediation="No action needed for this check.",
    ),

    # ------------------------------------------------------------------ response_determinism
    ("response_determinism", "pass"): CheckInterpretation(
        impact=(
            "Your server returns structurally consistent responses across multiple identical "
            "requests — same schema shape every time. AI agents can build reliable parsing "
            "logic against your tools. Integration tests will not produce false failures from "
            "response variance."
        ),
        remediation="No action needed.",
        reproduce="",
    ),
    ("response_determinism", "degraded"): CheckInterpretation(
        impact=(
            "Response structure is mostly consistent but varies on some fields across identical "
            "requests. AI agents that rely on specific fields being present may encounter "
            "KeyError / attribute-missing failures intermittently. Integration tests that "
            "check response structure will flake. The inconsistency is usually caused by "
            "conditional fields that appear only in some code paths."
        ),
        remediation=(
            "1. Audit your tool response models — ensure every field is always present, "
            "   even if null. Prefer null over absent.\n"
            "2. Use Pydantic or dataclasses to enforce a fixed response shape.\n"
            "3. Test: call the same tool 10 times and assert response schemas are identical."
        ),
        refs=["https://fynor.tech/docs/checks/response-determinism#remediation"],
    ),
    ("response_determinism", "fail"): CheckInterpretation(
        impact=(
            "Response structure varies significantly across identical requests. The JSON schema "
            "shape is not consistent — fields appear, disappear, or change type between calls. "
            "AI agents cannot build reliable tool call logic against this server. Every tool "
            "call is a guess about what fields will be present. Agents will hallucinate fields "
            "that were present in training but absent in the current response. Integration "
            "code will break unpredictably."
        ),
        remediation=(
            "1. Define a fixed Pydantic/dataclass response model for every tool.\n"
            "2. All optional fields must be declared Optional[type] = None — always present, "
            "   never absent.\n"
            "3. Remove any code path that conditionally adds or removes response fields.\n"
            "4. Run 10 identical calls to each tool and diff the response schemas:\n"
            "   python -c \"import json; print(set(json.loads(r1).keys()) ^ set(json.loads(r2).keys()))\"\n"
            "5. Add a response schema validation test to your CI pipeline."
        ),
        refs=["https://fynor.tech/docs/checks/response-determinism#remediation"],
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def interpret(result: CheckResult) -> CheckInterpretation | None:
    """
    Return the CheckInterpretation for a given CheckResult.

    Looks up (check_name, band) where band is derived from result.result and result.score.
    Returns None if no interpretation is registered for this check/band combination.

    Band mapping:
      result="na"        → "na"
      score == 100       → "pass"
      score >= 60        → "degraded"   (passes threshold but not excellent)
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

    return _TABLE.get((result.check, band))


def interpret_all(results: list[CheckResult]) -> dict[str, CheckInterpretation | None]:
    """
    Return interpretations for a list of CheckResults, keyed by check name.

    Convenience wrapper for CLI and API display.
    """
    return {r.check: interpret(r) for r in results}
