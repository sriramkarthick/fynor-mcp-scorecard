# Prompt Template — Adding a New Check

# Copy this entire block and fill in the [BRACKETS]. Paste into Claude Code.

---

Read .claude/context/02-checks-catalog.md and .claude/context/03-data-schemas.md first.

Add a new check to fynor/checks/[INTERFACE_TYPE]/[CHECK_NAME].py

Check details:
- Check ID:       [TYPE_###]                          e.g. REST_003
- Name:           [human-readable name]               e.g. "Pagination Completeness"
- Failure code:   [TYPE_###_DESCRIPTOR]               e.g. REST_003_PAGINATION_BROKEN
- Bucket:         [Security | Reliability | Performance]
- Severity:       [CRITICAL | HIGH | MEDIUM | LOW]
- What it detects: [one sentence describing what is checked]
- Agent failure mode: [what breaks in an AI agent when this check fails]
- How to test it: [what HTTP call or mock scenario proves pass vs. fail]

Implementation requirements:
1. Import and return CheckResult from fynor.checks (see 03-data-schemas.md for exact fields)
2. Use httpx for all HTTP calls — never requests
3. Docstring on the check function must explain the AGENT failure mode, not human failure mode
4. score: 0 = complete failure, 100 = perfect pass. Score 0-100 as a float, return as int.
5. When passed=True: failure_code=None, remediation=None
6. When passed=False: failure_code=[TYPE_###_DESCRIPTOR], remediation=[specific fix string]
7. metadata dict must contain the raw data used to make the pass/fail decision

Also write: tests/test_[interface_type]/test_[check_name].py
Requirements for tests:
- Use httpx.MockTransport — no real network calls
- Passing case: service behaves correctly -> check passes -> score >= 80
- Failing case: service shows the failure mode -> check fails, correct failure_code returned
- Unreachable case: connection refused or timeout -> check fails with CRITICAL or HIGH severity
- Assert: check_id, passed, failure_code, score, severity, remediation are all correct

Follow the pattern from: fynor/checks/mcp/response_time.py and tests/test_mcp/test_response_time.py

---
