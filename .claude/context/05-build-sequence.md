# Build Sequence — Month by Month, File by File

## Month 1 = May 2026. Month 6 = November 2026.

---

## NOW (Before Month 6) — Immediate Actions

Files already in repo (verify these exist and are correct):
- README.md          ✓ (full platform scope, all 7 interface types)
- pyproject.toml     ✓ (pip install fynor, click entry point)
- .gitignore         ✓
- LICENSE            ✓ (MIT)
- fynor/__init__.py  ✓ (VERSION = "0.0.1-dev")
- fynor/checks/mcp/__init__.py   ✓
- fynor/ontology/__init__.py     ✓
- fynor/report/__init__.py       ✓
- tests/__init__.py  ✓

Files to rename (identified in Review session):
- fynor/checks/cli_tool/ -> fynor/checks/cli/ (README shows cli/, not cli_tool/)

Files to add next (pyproject.toml already exists):
- CLAUDE.md (done — this session)
- .claude/context/* (done — this session)

---

## Month 6 — v0.1 (MCP checks + CLI, 19 files)

Build in this exact order (each file depends on the previous):

1. fynor/checks/__init__.py
   Content: CheckResult + AuditResult dataclasses, Severity + InterfaceType enums
   This is the CONTRACT that every other file depends on. Build it first.
   Reference: .claude/context/03-data-schemas.md for exact code.

2. fynor/checks/base.py
   Content: BaseChecker abstract class with check() method signature
   All 40 checkers inherit from this.

3. fynor/checks/runner.py
   Content: CheckRunner — takes AuditRequest, routes to correct checkers, returns List[CheckResult]
   Runs security checks on all interface types automatically.

4. fynor/checks/mcp/response_time.py   <- MCP_001_HIGH_LATENCY
5. fynor/checks/mcp/error_rate.py      <- MCP_002_HIGH_ERROR_RATE
6. fynor/checks/mcp/schema_validation.py <- MCP_003_SCHEMA_DRIFT
7. fynor/checks/mcp/retry_behavior.py  <- MCP_004_NO_RETRY_ON_TRANSIENT
8. fynor/checks/mcp/auth_token.py      <- MCP_005_AUTH_TOKEN_LEAKED
9. fynor/checks/mcp/rate_limit.py      <- MCP_006_RATE_LIMIT_ABSENT
10. fynor/checks/mcp/timeout_handling.py <- MCP_007_TIMEOUT_HANG
11. fynor/checks/mcp/log_completeness.py <- MCP_008_LOG_INCOMPLETE

12. fynor/scorer.py
    Content: 30/40/30 weighted aggregator, severity multipliers, grade computation
    Reference: .claude/context/03-data-schemas.md for exact logic.

13. fynor/report/terminal.py
    Content: rich tables + color-coded scores; pass/fail per check; letter grade prominent

14. fynor/report/json_report.py
    Content: AuditResult -> JSON string (machine-readable for CI/CD consumption)

15. fynor/cli.py
    Content: click CLI — fynor run --url X --type mcp [--format json|terminal] [--domain X]

16. tests/conftest.py
    Content: shared fixtures — mock MCP server using httpx.MockTransport

17. tests/test_mcp/test_response_time.py   <- first test ever
18. tests/test_mcp/test_auth_token.py      <- most important check
19. .github/workflows/ci.yml               <- pytest on every push

Ship: pip install fynor && fynor run --url https://any-mcp-server.com --type mcp
HN post: "Show HN: MCP Server Reliability Scorecard — 8 deterministic checks, open source"

---

## Month 7 — Python SDK (2 files)

20. fynor/__init__.py
    Content: from fynor import run, AuditResult, CheckResult (public API)
    Usage: result = await run(url="...", type="mcp")

21. docs/sdk-quickstart.md
    Content: 5-minute guide for Python developers using fynor as a library

---

## Month 8 — GitHub Action (2 files)

22. action.yml
    Content: GitHub Action manifest — runs fynor check on PR

23. .github/workflows/publish.yml
    Content: auto-publish to PyPI on git tag push (v0.1, v0.2, etc.)
    Uses PyPI Trusted Publisher — no API key stored in repo.

---

## Month 9 — REST + Security + Hosted UI (18 files)

REST checks:
24. fynor/checks/rest/schema_stability.py    <- REST_001
25. fynor/checks/rest/burst_rate_limit.py    <- REST_002
26. fynor/checks/rest/pagination.py          <- REST_003
27. fynor/checks/rest/idempotency.py         <- REST_004
28. fynor/checks/rest/error_readability.py   <- REST_005
29. fynor/checks/rest/auth_expiry.py         <- REST_006

Security checks (cross-cutting):
30. fynor/checks/security/credential_headers.py <- SEC_001
31. fynor/checks/security/secret_in_url.py      <- SEC_002
32. fynor/checks/security/tls_enforcement.py    <- SEC_003
33. fynor/checks/security/permissions.py        <- SEC_004
34. fynor/checks/security/pii_in_errors.py      <- SEC_005
35. fynor/checks/security/cors.py               <- SEC_006

Tests:
36. tests/test_rest/ (6 test files)
37. tests/test_security/ (6 test files)

REST API + Hosted UI:
38. fynor/api.py            <- FastAPI: POST /v1/audit, GET /v1/audit/{id}
39. frontend/               <- Next.js 14 app (scorecard.fynor.dev)
40. Deploy: Vercel + Railway + Supabase

Ship: scorecard.fynor.dev live. Shareable report URL: scorecard.fynor.dev/r/{audit_id}
Milestone: 20 checks total. First managed signups ($49/month via Stripe).

---

## Month 12 — GraphQL + WebSocket + MCP SERVER (14 files)

GraphQL checks:
41. fynor/checks/graphql/schema_drift.py      <- GQL_001
42. fynor/checks/graphql/depth_limit.py       <- GQL_002
43. fynor/checks/graphql/n_plus_one.py        <- GQL_003
44. fynor/checks/graphql/subscription.py      <- GQL_004

WebSocket checks:
45. fynor/checks/websocket/reconnect.py       <- WSS_001
46. fynor/checks/websocket/heartbeat.py       <- WSS_002
47. fynor/checks/websocket/ordering.py        <- WSS_003
48. fynor/checks/websocket/backpressure.py    <- WSS_004

Tests:
49. tests/test_graphql/ (4 test files)
50. tests/test_websocket/ (4 test files)

MCP Server (ADR-05 — polished, not rushed):
51. fynor/mcp_server.py
    Content: Fynor exposes 5 tools to AI agents:
    - run_audit(url, type, domain) -> AuditResult
    - get_remediation(failure_code) -> fix string
    - compare_audits(before_id, after_id) -> diff
    - get_audit_status(audit_id) -> progress
    - list_failure_patterns(domain, top_n) -> patterns

52. tests/test_mcp_server.py

Ship: v0.3 — 28 checks. Fynor is now an MCP server. AI agents can audit autonomously.
Milestone target: 500 GitHub stars.

---

## Month 15 — gRPC + SOAP + Phase C Groundwork (15 files)

gRPC checks:
53. fynor/checks/grpc/proto_compatibility.py   <- GRPC_001
54. fynor/checks/grpc/stream_cancellation.py   <- GRPC_002
55. fynor/checks/grpc/deadline_propagation.py  <- GRPC_003
56. fynor/checks/grpc/retry_unavailable.py     <- GRPC_004

SOAP checks:
57. fynor/checks/soap/wsdl_drift.py            <- SOAP_001
58. fynor/checks/soap/fault_readability.py     <- SOAP_002
59. fynor/checks/soap/ws_security.py           <- SOAP_003

Tests:
60. tests/test_grpc/ (4 test files)
61. tests/test_soap/ (3 test files)

Phase C groundwork:
62. fynor/ontology/loader.py      <- loads JSON rules from ontologies/ folder
63. fynor/ontology/evaluator.py   <- checks agent_decision against rule conditions
64. ontologies/fintech_trading.json <- first 20 domain rules (FinTech trading compliance)
65. fynor/report/pdf.py           <- PDF report generation for enterprise

Ship: v0.4 — 35 checks. Phase C pilot: first $5K manual audit.
Milestone: "Request full audit" clicks: 50. Phase C demand validated.

---

## Month 18 — CLI Checks + v1 Platform (9 files)

CLI checks:
66. fynor/checks/cli/exit_code.py           <- CLI_001
67. fynor/checks/cli/json_output.py         <- CLI_002
68. fynor/checks/cli/determinism.py         <- CLI_003
69. fynor/checks/cli/stdin_support.py       <- CLI_004
70. fynor/checks/cli/version_flag.py        <- CLI_005

Tests:
71. tests/test_cli/ (5 test files)

Platform:
72. Stripe billing integrated (managed $49/month, enterprise invoicing)
73. First $5K paid audit completed + documented
74. Phase C: begin building ground_truth_labels table with first labeled decisions

Ship: v0.5 — 40 checks. All interface types covered.

---

## Month 20 — v1.0 Unified Platform

75. Full Next.js dashboard (score history, trend charts, multi-check UI)
76. GitHub Action polished + documentation site
77. Docker image published (docker run fynor/fynor run --url X --type mcp)
78. npm package published (npx fynor run --url X --type mcp)
79. All 40 checks passing in CI on every push
80. 2,000 GitHub stars target

Ship: v1.0 — HN "Show HN" post + Product Hunt launch.

---

## Phase C First Hire (at $500K ARR, Year 3 = 2029)
First engineer (remote, India):
- Maintains and extends Phase C platform
- Builds ground truth labeling interface
- Adds second vertical (healthcare_clinical.json)
Funded from Phase C revenue.

## Phase C Staffing Thresholds
$500K ARR (Year 3):  first engineer (remote, India)
$2M ARR (Year 4):    second engineer OR first sales/CS hire
$5M ARR (Year 5):    2-3 engineers + 1 sales (team of 4-6)
$10M+ ARR (Year 6):  CTO + VP Sales (exit-ready structure)
At exit ($15-20M ARR): 8-15 employees total

## Weekly Hour Budget (hard ceiling: 21 hrs/week at 3 hrs/day)
Month 1-5 (learning-heavy):
  Technical learning (certs, skills): 10 hrs/week
  Phase B product development: 3 hrs/week
  Technical writing: 2 hrs/week
  Domain research: 2 hrs/week
  Total: ~17 hrs/week

Month 6-12 (split):
  Phase A client delivery: 5-7 hrs/week
  Phase B product: 5 hrs/week
  Technical learning: 5 hrs/week
  Writing + domain: 3 hrs/week
  Total: ~18-20 hrs/week
