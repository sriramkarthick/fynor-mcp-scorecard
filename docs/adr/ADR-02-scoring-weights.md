# ADR-02: Scoring Weights — Security 30% + Reliability 40% + Performance 30%

**Status:** Accepted and Locked  
**Date:** 2026-05-13  
**Deciders:** Sriram Karthick (Fynor Technologies)  
**Do not change without a superseding ADR.**

---

## Context

Eight checks across three categories produce individual 0-100 scores. A weighted
grade must combine them into a single letter grade (A through F). The weights
determine how much each category contributes to the final score.

The scoring system must satisfy three requirements:

1. **Reproducibility:** The same check results always produce the same grade
2. **Severity ordering:** Security failures must be treated more harshly than performance issues
3. **Interpretability:** A developer should be able to look at the category scores and understand why they received their grade

---

## Weight Options Considered

| Option | Security | Reliability | Performance | Rationale |
|--------|----------|-------------|-------------|-----------|
| Equal  | 33%      | 33%         | 33%         | No severity ordering — rejected |
| SRE-aligned | 25% | 50%        | 25%         | Reliability-heavy, de-emphasises security — rejected |
| **ADR-02 (chosen)** | **30%** | **40%** | **30%** | Balanced with reliability lead and security/performance symmetry |
| Security-heavy | 50% | 30%    | 20%         | Overweights security for non-regulated use cases — rejected |

---

## Decision: 30% / 40% / 30%

### Reliability at 40% — highest weight

Reliability is the primary purpose of the platform. Four of the eight checks
measure reliability directly: `error_rate`, `schema`, `retry`, `log_completeness`,
and `timeout`. An unreliable server cannot serve AI agents regardless of how
fast or secure it is.

This weight aligns with the Google SRE "four golden signals" framework (Beyer et al., 2016),
which treats error rate and availability as the primary indicators of service health.
In the agent context, reliability failures are compounding — a single schema violation
at call #23 in a 50-step pipeline corrupts the entire prior execution context.
No other failure type has this cascading property at the same rate.

### Security at 30% — tied with performance

Security failures are binary and catastrophic. A server that leaks credentials or
accepts unauthenticated calls is not "slightly insecure" — it is a pipeline-level
vulnerability. This is addressed by the **security cap rule** (below), which handles
the absolute-failure case separately from the weighted score.

The 30% weight governs the graduated case: a server with partial authentication
enforcement (e.g., returns 401 but has no rate limiting on auth endpoints) should
receive a measurable penalty below the catastrophic threshold.

The 30% weight is consistent with NIST SP 800-160 (Ross et al., 2016), which
positions security as a cross-cutting concern that modifies reliability rather
than replacing it.

### Performance at 30% — tied with security

Performance failures (high latency, missing rate limits) are recoverable. An agent
pipeline can implement retry logic with backoff. It cannot recover from a corrupt
schema or a leaked credential. The equal weighting of security and performance
reflects that both are important but secondary to reliability.

The 30% performance weight aligns with the Apdex (Application Performance Index)
framework (Sevcik & Wetzel, 2005), which treats performance as one factor in a
composite score rather than the primary signal.

---

## The Security Cap Rule

**If any security check scores 0, the final weighted score is capped at 59.0 (maximum grade: D).**

This rule exists because the weighted average obscures catastrophic security failures.
A server scoring 0 on `auth_token` but 100 on all other checks would receive a
weighted score of 70 (grade C) under the raw weights. This is incorrect: a server
that accepts unauthenticated calls should never be recommended for production use,
regardless of its latency.

The cap threshold of 59.0 (grade D boundary) was chosen to:
1. Signal clearly that the server is not production-safe
2. Allow a non-zero score so the developer can see which other checks passed
3. Prevent a false-negative where a developer interprets "no grade" as "not tested"

**This rule is not a weight — it is a hard constraint that overrides the weights.**
It is implemented as a post-computation adjustment in `scorer.py`, not as a
weight modification, to preserve interpretability of the category scores.

---

## Check-to-Category Mapping

| Check | Category | Weight Contribution | Justification |
|-------|----------|---------------------|---------------|
| `latency_p95` | Performance | 30% / 2 = 15% | Latency is a performance golden signal (Beyer et al., 2016) |
| `error_rate` | Reliability | 40% / 5 = 8% | Errors are a reliability golden signal |
| `schema` | Reliability | 40% / 5 = 8% | Schema violations are correctness failures |
| `retry` | Reliability | 40% / 5 = 8% | Malformed-input handling is a correctness property |
| `auth_token` | Security | 30% / 1 = 30% | Auth is the sole security check in v0.1; weight is undivided |
| `rate_limit` | Performance | 30% / 2 = 15% | Rate limiting is a saturation/traffic golden signal |
| `timeout` | Reliability | 40% / 5 = 8% | Hard hangs are the most severe availability failure |
| `log_completeness` | Reliability | 40% / 5 = 8% | Audit logs are a reliability and compliance property |

Note: As more security checks are added (v0.2+), the `auth_token` weight of 30%
is divided equally among all security checks. The category weight stays at 30%.

---

## Grade Band Justification

| Grade | Range | Interpretation |
|-------|-------|----------------|
| A | 90–100 | All category scores above 90. Agent-safe for production. |
| B | 75–89 | Minor issues in one category. Safe with monitoring. |
| C | 60–74 | Moderate issues. Investigate before production. |
| D | 45–59 | Significant failures, or security cap applied. Not recommended. |
| F | 0–44 | Critical failures across multiple categories. Do not use. |

The band boundaries are symmetric around the midpoint (50%) and spaced to provide
meaningful differentiation. A system with a score of 74 (C) has materially different
risk from one scoring 76 (B), and the developer should be able to act on this.

---

## Consequences

**Positive:**
- Category scores give developers actionable signals (e.g., "your reliability is 45 — focus there")
- The security cap prevents grade inflation for broken auth
- Weights are stable and can be cited in external documentation and academic work

**Negative:**
- A single `auth_token` check carries the full 30% security weight in v0.1 — adding more security checks in v0.2 will dilute its individual contribution
- The 40% reliability weight means a server with poor logging and schema issues can score C even with perfect auth and latency

**Future consideration:** When v0.2 ships (REST + Security checks), the security
check count increases. The category weight stays at 30%. Individual check weights
decrease proportionally. This may require a recalibration ADR if the distribution
produces unintuitive grades.

---

## References

- Beyer, B. et al. (2016). *Site Reliability Engineering*. O'Reilly. Chapter 6: Monitoring Distributed Systems.
- Ross, R. et al. (2016). *Systems Security Engineering*. NIST SP 800-160.
- Sevcik, P. & Wetzel, J. (2005). *Understanding Apdex*. NetForecast.
- Lyu, M.R. (1995). *Handbook of Software Reliability Engineering*. IEEE CS Press.
