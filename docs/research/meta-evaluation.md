# Fynor Meta-Evaluation: How Fynor Evaluates Itself

**Last updated:** 2026-05-13

---

## The Problem Statement

Every evaluation tool faces the same recursive challenge: *who evaluates the
evaluator?* For Fynor, this is not a philosophical question — it is an operational
one with specific, measurable dimensions.

If Fynor grades an MCP server as A (95/100) and that server subsequently causes
a production AI pipeline failure, Fynor has failed. The question is: *which part
of Fynor failed, and how do we detect and fix it?*

This document defines Fynor's self-evaluation framework — the methods by which
Fynor measures its own reliability.

---

## Four Meta-Evaluation Dimensions

### Dimension 1: Check Accuracy (Does each check measure what it claims?)

**The question:** When `auth_token` scores 0 (critical failure), does the server
actually have an exploitable authentication vulnerability?

**Measurement method:**
- Ground truth: manual security audit of N servers that received `auth_token` = 0
- Metric: precision (what fraction of 0-score auth_token flags are genuine vulnerabilities?)
- Target: precision ≥ 0.90

**Known failure modes for each check:**

| Check | False Positive Cause | False Negative Cause |
|-------|---------------------|---------------------|
| `latency_p95` | Network congestion on Fynor's side | Server using connection pooling that warms up after first N requests |
| `error_rate` | Server rate-limiting Fynor (returns 429, counted as error) | Server returning 200 with error payload |
| `schema` | Server using extended JSON-RPC 2.0 fields (valid extension, wrong check) | Schema check only validates envelope, not field types |
| `retry` | Server returning 400 for valid reasons unrelated to JSON-RPC | Server returning 200 with error object (technically passes, semantically fails) |
| `auth_token` | Server legitimately echoes a derived (non-sensitive) token | Server using non-standard auth header names not in pattern list |
| `rate_limit` | Server rate-limiting by IP, not by API key (Fynor's IP gets blocked) | Server implementing soft rate limiting without 429 |
| `timeout` | Fynor's infrastructure issue, not the target server | Server responds within 5s but hangs on connection teardown |
| `log_completeness` | Fynor probes wrong endpoints (non-standard paths) | Server logs on endpoints not in Fynor's probe list |

**Action on false positive/negative discovery:** File a new ADR section under
ADR-03 documenting the failure mode. Redesign the check sub-algorithm. Increment
check version (`check_schema_v2`).

---

### Dimension 2: Score Reproducibility (Does the same server always get the same grade?)

**The question:** If we run Fynor against server X today and again in 1 hour with
no server changes, do we get the same grade?

**Measurement method:**
- Run checks against N=20 MCP servers, 5 times each at 1-hour intervals
- Compute within-server coefficient of variation (CV) for each check score
- Target CV for deterministic checks: 0%
- Target CV for probabilistic checks: < 10%

**Documented variance sources and mitigations:**

| Source | Affected Checks | Mitigation |
|--------|----------------|------------|
| Network latency variance | `latency_p95` | P95 over 20 requests smooths transient spikes. ±15% documented. |
| Probabilistic server errors | `error_rate` | 50-request window. Binomial variance at 5% error rate over n=50 is ±3.1%. |
| Server state changes | All | Certification requires 30 consecutive days — one lucky run cannot certify |
| Fynor infrastructure variance | All | Check workers use ephemeral ECS tasks with consistent network config |

**Grade stability rule:** A server's grade should not change by more than one
letter (e.g., A to B or B to A) between consecutive runs absent a genuine server
change. If this happens, the affected check's algorithm is reviewed.

---

### Dimension 3: Certification Validity (Do certified servers actually perform better?)

**The question:** Does holding an Agent-Ready certificate correlate with lower
rates of AI pipeline failures in production?

This is the ultimate validity question for the platform. If certified servers
fail at the same rate as uncertified servers, the certification is meaningless.

**Measurement method (Study 3, Month 18):**
- Cohort A: N=10 MCP servers that held Agent-Ready certification for ≥60 days
- Cohort B: N=10 MCP servers that applied for certification but failed to achieve it
- Outcome measure: number of AI pipeline failures per 10,000 agent calls (reported by users)
- Statistical test: two-sample Fisher's exact test, α=0.05
- Confounders to control: server age, call volume, domain type

**Expected result:** Certified servers have statistically fewer pipeline failures.
If not, the check taxonomy is missing a failure mode that the uncertified cohort
is exploiting.

**Honest baseline:** This study requires client participation (self-reported
pipeline failures). The first version will have small N and limited statistical
power. It establishes the methodology, not a definitive result.

---

### Dimension 4: Self-Learning Validity (Does the self-learning loop improve checks?)

**The question:** After Junction 2 proposes a new detection algorithm and it
is approved and deployed, does the pattern detector produce better predictions?

**Measurement method:**
- Track precision and recall of the pattern detector over time
- Metric: for each detected pattern, does it match a subsequent confirmed failure?
- Target: pattern precision > 0.70 (70% of detected patterns are confirmed real)
- Track: pattern precision before and after each Junction 2 update

**Feedback loop validity:** The self-learning loop is only valid if the patterns
it produces lead to genuine improvements in check design (Junction 2) or domain
ontology coverage (Junction 3). Validity is measured by whether approved patterns
reduce the rate of novel (unclassified) failures over time.

---

## Fynor's Own Reliability Grade

Fynor's hosted API is itself subject to the same reliability requirements it
enforces on others. Fynor runs checks against its own endpoints monthly and
publishes the results at `https://status.fynor.tech/reliability`.

Fynor's own Agent-Ready certification target: **Grade A, Month 24.**

This is not optional. A reliability platform that cannot pass its own reliability
checks has zero credibility.

**Current self-check status:**
- `latency_p95`: Not yet measured (hosted service not yet launched)
- `error_rate`: Not yet measured
- `auth_token`: Designed to pass (API key validation required on all endpoints)
- `rate_limit`: Designed to pass (rate limiting implemented at API Gateway level)
- `schema`: N/A (REST API, not MCP) — v0.2 REST checks will apply
- `log_completeness`: Designed to pass (CloudTrail + application logs)

---

## The Circular Evaluation Guard

Fynor uses the Claude API for Junction 1 (Failure Interpretation Agent). This
creates a potential circular evaluation: Fynor uses an AI to interpret failures
in AI-facing infrastructure.

The guard against this circularity is architectural:

1. The Claude API call is never on the measurement critical path. Measurements
   are deterministic and complete before any AI is invoked.
2. The output of Junction 1 is a proposal, never an action. A human must approve
   every interpretation before it enters the pattern library.
3. The Claude API's reliability is measurable using Fynor's own REST checks (v0.2).
   Fynor will run reliability checks against the Anthropic API as a standard target.

**If the Claude API fails:** Junction 1 produces a "pending" interpretation.
Check results are unaffected. The measurement system continues operating without
the AI layer.

This is the operational proof of the ADR-01 governing principle: the automation
spine is independent of the AI junctions. Remove all three AI junctions and Fynor
still measures, scores, and certifies. The AI junctions add intelligence; they
do not provide reliability.

---

## Meta-Evaluation Schedule

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Check false positive/negative review | Monthly | Sriram Karthick |
| Score reproducibility measurement (N=20) | Quarterly | Engineering |
| Pattern detector precision tracking | Weekly (automated) | Automated via history.jsonl |
| Fynor self-check run | Monthly | Automated |
| Certification validity study (Study 3) | Month 18 (one-time, then annually) | Research |
| Ground truth database growth review | Monthly | Engineering + Domain Expert |

---

## Publication Commitment

The results of Studies 1, 2, and 3 will be published regardless of outcome.
Negative results (checks that fail to achieve their accuracy targets) are as
important as positive results for the scientific credibility of the framework.

A reliability platform that only publishes its successes has the same problem
as the evaluation tools it was designed to replace.
