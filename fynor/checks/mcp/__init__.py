"""
fynor.checks.mcp — 8 deterministic reliability checks for MCP servers.

All 8 checks are binary pass/fail. No LLM judgment. Same input → same output.
Each check returns a CheckResult with a score (0–100), pass/fail, and detail.

Check index:
  1. latency_p95       — P95 response time under 20-request load
  2. error_rate        — Error percentage over a 50-request window
  3. schema            — MCP spec compliance (JSON-RPC 2.0 envelope validation)
  4. retry             — Graceful handling of malformed / duplicate requests
  5. auth_token        — Credential handling: no leakage, correct 401 on missing auth
  6. rate_limit        — 429 + Retry-After returned on burst (100 req/s)
  7. timeout           — Graceful error returned on connection kill at 5s
  8. log_completeness  — Structured, queryable audit log exposure

Scoring weights (ADR-02, locked):
  Security    (auth_token)                             — 30%
  Reliability (error_rate, schema, retry, timeout,     — 40%
               log_completeness)
  Performance (latency_p95, rate_limit)                — 30%
"""

from fynor.checks.mcp.latency import check_latency_p95
from fynor.checks.mcp.auth import check_auth_token
from fynor.checks.mcp.error_rate import check_error_rate
from fynor.checks.mcp.schema import check_schema
from fynor.checks.mcp.retry import check_retry
from fynor.checks.mcp.rate_limit import check_rate_limit
from fynor.checks.mcp.timeout import check_timeout
from fynor.checks.mcp.log_completeness import check_log_completeness

ALL_CHECKS = [
    check_latency_p95,
    check_error_rate,
    check_schema,
    check_retry,
    check_auth_token,
    check_rate_limit,
    check_timeout,
    check_log_completeness,
]

__all__ = [
    "check_latency_p95",
    "check_error_rate",
    "check_schema",
    "check_retry",
    "check_auth_token",
    "check_rate_limit",
    "check_timeout",
    "check_log_completeness",
    "ALL_CHECKS",
]
