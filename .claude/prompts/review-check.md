# Prompt Template — Reviewing a Check for Production Quality

# Copy this block, fill in [BRACKETS], paste into Claude Code.

---

Read .claude/context/02-checks-catalog.md and .claude/context/03-data-schemas.md first.

Review fynor/checks/[INTERFACE_TYPE]/[CHECK_NAME].py for production quality.

Check the following, in order:

1. CONTRACT COMPLIANCE
   - Does it return CheckResult with ALL required fields?
     check_id, interface_type, name, score, passed, severity, failure_code, remediation, metadata
   - Is severity a Severity enum value (not a plain string)?
   - Is failure_code None when passed=True?
   - Is remediation None when passed=True?
   - Does it use httpx (not requests)?

2. AGENT FAILURE MODE ACCURACY
   - Does the docstring explain why AGENTS fail (not humans)?
   - Does the check actually detect the agent-specific failure mode?
     Reference: .claude/context/02-checks-catalog.md for the expected failure mode.
   - Would a human-use testing tool miss this failure? (It should — that's Fynor's value)

3. SCORE CALIBRATION
   - Does score=0 for complete failure (service is broken for agents)?
   - Does score=100 for perfect pass?
   - Is the scoring gradual and meaningful between 0-100?
   - Would a service with a minor version of this issue get a proportional score?

4. REMEDIATION QUALITY
   - Is the remediation specific? ("Add Redis cache layer" NOT "improve performance")
   - Does it give an actionable fix that a developer can implement?
   - Does it estimate the impact? ("reduces P95 by ~60%" if known)

5. METADATA COMPLETENESS
   - Does metadata contain the raw data used to make the decision?
   - Can a developer look at metadata and understand WHY the check passed/failed?
   - Example: { "p95_ms": 2847, "threshold_ms": 2000, "sample_count": 20 }

6. ERROR HANDLING
   - What happens when the target server is unreachable?
   - What happens when the response is malformed?
   - Does the check fail gracefully with a CheckResult (not raise an exception)?

7. TEST COVERAGE
   - Does tests/test_[interface_type]/test_[check_name].py exist?
   - Does it cover: passing case, failing case, unreachable case?
   - Are all assertions present (check_id, passed, failure_code, score, severity)?

Report format:
  PASS/FAIL for each of the 7 areas.
  For each FAIL: exact line number + what to fix.
  Final verdict: PRODUCTION READY or NEEDS FIX (with priority list).

---
