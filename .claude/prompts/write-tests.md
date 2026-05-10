# Prompt Template — Writing Tests for a Check

# Copy this block, fill in [BRACKETS], paste into Claude Code.

---

Write pytest tests for fynor/checks/[INTERFACE_TYPE]/[CHECK_NAME].py

Check being tested:
- Check ID:       [TYPE_###]
- Failure code:   [TYPE_###_DESCRIPTOR]
- Severity:       [CRITICAL | HIGH | MEDIUM | LOW]
- What it checks: [one sentence]

Test file location: tests/test_[interface_type]/test_[check_name].py

Requirements:
1. No real network calls — use httpx.MockTransport or pytest monkeypatch
2. Minimum three test cases:
   a. PASSING CASE
      - Mock: service behaves correctly
      - Assert: check.passed == True
      - Assert: check.score >= 80
      - Assert: check.failure_code is None
      - Assert: check.remediation is None
   b. FAILING CASE
      - Mock: service shows the specific failure mode
      - Assert: check.passed == False
      - Assert: check.failure_code == "[TYPE_###_DESCRIPTOR]"
      - Assert: check.severity == Severity.[LEVEL]
      - Assert: check.remediation is not None (must give a specific fix)
      - Assert: check.score <= 40
   c. UNREACHABLE CASE
      - Mock: connection refused OR timeout
      - Assert: check.passed == False
      - Assert: check.severity in (Severity.CRITICAL, Severity.HIGH)
      - Assert: check.score == 0

3. Use conftest.py fixtures for shared mock server setup
4. Each test function name: test_[check_name]_passes / test_[check_name]_fails / test_[check_name]_unreachable
5. Docstring on each test explaining what scenario it covers

Reference for fixture patterns: tests/conftest.py
Reference for check import patterns: tests/test_mcp/test_response_time.py

---
