# Fynor: A Deterministic Reliability Measurement Framework for AI Agent Interfaces

**Sriram Karthick**  
Fynor Technologies, Thiruppuvanam, Tamil Nadu, India  
sriram@fynor.tech

---

## Abstract

AI agents increasingly depend on external interfaces — APIs, MCP servers, and
command-line tools — designed for human traffic patterns. These interfaces exhibit
failure modes that are silent, compounding, and catastrophic under machine-speed
access without human error recovery. Existing reliability measurement frameworks
(Postman, Datadog, Prometheus) were built for human-facing software and cannot
detect these agent-specific failure modes.

We present **Fynor**, a reliability measurement framework that defines and
operationalizes eight agent-specific failure modes across three signal categories
derived from industry-standard SRE literature: availability (error rate, timeout),
correctness (schema compliance, malformed-input handling, audit completeness), and
security (credential exposure, authentication enforcement, rate limiting). Our
deterministic scoring engine produces reproducible letter grades (A through F)
without LLM judgment, directly addressing the reproducibility failures observed
in existing AI evaluation tools.

We introduce the **Automation Spine + AI Agent Junction** architecture, which
separates statistical pattern detection (fully deterministic) from intelligent
failure interpretation (LLM-backed with mandatory human review gate). This
separation prevents circular AI evaluation while enabling continuous self-improvement.

Finally, we describe the **Ground Truth Database** construction methodology — a
labeled corpus of AI agent decision correctness annotated by domain experts —
which provides the external ground truth that current AI evaluation frameworks
lack. We argue that this methodology produces a data asset that compounds in
value with each client deployment and is structurally irreproducible by any
competitor without equivalent deployment history.

**Keywords:** AI agent reliability, MCP servers, interface testing, deterministic evaluation, ground truth, human-in-the-loop, software reliability engineering

---

## 1. Introduction

The emergence of the Model Context Protocol (MCP) as a standard interface between
AI agents and external services (Anthropic, 2024) marks a shift in how software is
consumed. AI agents do not call APIs the way humans do. Where a human developer
calls an API once to prototype and then a few times per hour in production, an AI
agent may call the same API thousands of times per minute, in pipeline chains where
a single failure at step k corrupts all prior computation, and without the ability
to read an error message and adapt.

This shift exposes a fundamental gap: **no existing reliability measurement tool
was designed to test whether an interface is safe for AI agent consumption.** The
industry's most capable tools — Postman (API functional testing), Datadog (service
observability), k6 (load testing), and PromptFoo (LLM output quality) — were all
built for human-facing software. None ask the agent-relevant question: *"Does this
MCP server behave correctly when called at 10,000 requests per minute, with
machine-generated inputs, and with no human error recovery?"*

This paper makes three contributions:

1. **A formal taxonomy of eight agent-specific failure modes** derived from the
   intersection of SRE golden signals (Beyer et al., 2016), Byzantine fault
   tolerance theory (Lamport et al., 1982), and NIST security engineering
   (Ross et al., 2016). We show that each failure mode is distinct, detectable
   without LLM judgment, and directly traceable to observable interface behavior.

2. **The Automation Spine + AI Agent Junction architecture**, a governance
   model for AI reliability platforms that separates deterministic measurement
   (no AI, fully reproducible) from intelligent interpretation (AI-backed,
   human-gated). This architecture directly addresses the circular evaluation
   problem: a reliability platform that uses AI for its core measurements
   inherits the same reliability failures it is designed to detect.

3. **The Ground Truth Database methodology**, which constructs a labeled corpus
   of correct vs. incorrect AI agent decisions through sequential domain expert
   annotation. We demonstrate that this methodology produces a compound-value
   data asset equivalent in structure (though not in domain) to the RLHF
   corpora that underlie modern LLM alignment.

---

## 2. Background and Related Work

### 2.1 Software Reliability Engineering

The foundational framework for service reliability measurement is the four golden
signals defined by Google's Site Reliability Engineering practice (Beyer et al., 2016):
latency, traffic, errors, and saturation. These signals are measured at the service
boundary and form the basis for all modern observability platforms.

Fynor's eight checks are a strict extension of the four golden signals to the
agent context: latency → `latency_p95`, errors → `error_rate`, traffic →
`rate_limit`, saturation → `timeout`. Four additional checks address correctness
(`schema`, `retry`), auditability (`log_completeness`), and security (`auth_token`)
— dimensions that the golden signals do not cover because they were not failure modes
for human-facing services.

Nygard's stability patterns (2007) identify timeout and circuit breaker as the
primary mechanisms for preventing cascading failures in distributed systems. The
`timeout` check directly tests whether a server will cause a cascading hang in an
agent pipeline.

### 2.2 Chaos Engineering

Chaos engineering (Basiri et al., 2016) systematically injects failures into
production systems to measure resilience. Fynor's `retry` and `rate_limit` checks
share the chaos engineering philosophy of testing with non-standard inputs, but
differ in two important ways:

1. **Controlled scope:** Chaos engineering runs in production. Fynor checks run
   against the target in isolation, without affecting production traffic.
2. **Agent-specific failure modes:** Chaos engineering tests system resilience
   to infrastructure failures (node crashes, network partitions). Fynor tests
   interface correctness under agent-generated inputs (malformed JSON-RPC,
   burst traffic without backoff).

### 2.3 AI Evaluation Tools

The AI evaluation literature has identified four persistent problems with
current evaluation tools (Liang et al., 2022; Bowman, 2023):

1. **Low reproducibility:** LLM-judged evaluations produce different results
   on repeated runs against the same input.
2. **Circular evaluation:** Using LLMs to evaluate LLM outputs introduces the
   same biases as the model under evaluation (Panickssery et al., 2024).
3. **Lack of ground truth:** Most evaluation frameworks measure alignment with
   human preferences estimated from small annotator pools, not from ground truth.
4. **Evaluation of capabilities, not reliability:** Existing benchmarks (MMLU,
   HumanEval, BIG-Bench) measure what an LLM can do, not whether the infrastructure
   it uses is reliable.

Fynor addresses problems 1 and 2 directly through its deterministic check design
(ADR-01). Problems 3 and 4 are addressed through the Ground Truth Database
methodology (Section 5).

### 2.4 Human-in-the-Loop Machine Learning

The HITL ML literature (Monarch, 2021; Zanzotto, 2019) establishes that the most
reliable automated systems are those that incorporate human judgment at specific
high-uncertainty decision points rather than attempting full automation.

Fynor's AI Agent Junction architecture instantiates this principle concretely:
three specific junctions (failure interpretation, pattern learning, ontology update)
require human approval before their outputs are acted on. This is functionally
equivalent to the "human-in-the-loop" annotation workflows used in active learning
systems (Settles, 2012).

---

## 3. Problem Formalization

### 3.1 Agent-Specific Failure Modes

**Definition 1 (Agent-facing interface).** An *agent-facing interface* I is any
software endpoint that an AI agent calls as part of an automated pipeline: a REST
API, MCP server, GraphQL endpoint, WebSocket stream, gRPC service, SOAP service,
or CLI tool.

**Definition 2 (Agent-specific failure mode).** A failure mode F of interface I
is *agent-specific* if and only if:
- F occurs primarily or exclusively under machine-speed, high-volume, or
  machine-generated-input conditions, AND
- F would not be detected by a human user calling I interactively, OR
- The consequences of F are qualitatively different for an AI agent than for a
  human user (specifically: an agent cannot recover from F by reading an error
  message and adapting).

Under this definition, all eight Fynor checks measure agent-specific failure modes.
We demonstrate for three:

**`latency_p95`:** A P95 latency of 4,000ms is acceptable for a human user who
calls an API occasionally. For an agent executing a 100-step pipeline with one
API call per step, the expected total latency is 400,000ms (6.7 minutes) — the
pipeline becomes unusable. Human users call an API infrequently enough that
P95 rarely matters. Agents hit P95 50 times per 1,000 calls.

**`retry`:** A server that returns HTTP 500 on malformed JSON-RPC input may
indicate a crash. A human developer receives the 500, inspects the request,
and fixes their client. An AI agent running in an automated pipeline sees the
500, marks the call as failed, and continues — potentially cascading the failure
through the remaining pipeline steps without any indication that the server
crashed rather than simply not finding a result.

**`auth_token`:** A server that includes the API key in the response's
`Authorization` header echoes the credential back to the caller. A human
developer might notice and discard this. An AI agent logs all responses,
may forward them to downstream systems, and cannot independently recognize
the security implication of receiving a credential it just sent.

### 3.2 The Reproducibility Requirement

**Definition 3 (Reproducible check).** A check C is *reproducible* if, for any
interface I in state S, running C against I produces the same score within a
defined variance band ε:

```
|C(I, S, run_1) - C(I, S, run_2)| ≤ ε
```

All eight Fynor checks are designed to be reproducible. The variance band ε
for each check:
- `latency_p95`: ±15% (inherent in network latency measurements)
- `error_rate`: ±5% (50-request window, binomial variance)
- `schema`, `retry`, `auth_token`, `log_completeness`: ε = 0 (deterministic binary outcomes)
- `rate_limit`: ε = 0 (binary: either 429 fires or it does not)
- `timeout`: ε = 0 (binary: either the request completes within 5s or it does not)

The reproducibility guarantee is what makes the Agent-Ready certification
meaningful: a server that passes 30 consecutive days of checks is genuinely
reliable, not lucky on a single run.

---

## 4. The Eight-Check Taxonomy

The eight checks are classified across three signal categories from the SRE
golden signals framework (Beyer et al., 2016) extended with Byzantine fault
tolerance correctness checks (Lamport et al., 1982):

| Signal Category | Check | Measurement | Agent-Specific Failure Detected |
|----------------|-------|-------------|--------------------------------|
| **Availability** | `error_rate` | Non-2xx rate over 50 requests at 1 req/s | Silent failures accumulate in pipeline chains |
| **Availability** | `timeout` | Whether a response arrives within 5s | Hard hangs block the entire pipeline thread |
| **Correctness** | `schema` | JSON-RPC 2.0 envelope compliance | Structural errors are unrecoverable without human inspection |
| **Correctness** | `retry` | Server behavior on malformed input | Pipeline crashes on agent-generated edge-case inputs |
| **Correctness** | `log_completeness` | Structured audit trail presence | Regulated AI deployments require non-repudiable audit logs |
| **Security** | `auth_token` | Credential leakage + 401 enforcement | Agents propagate leaked credentials through pipeline logs |
| **Performance** | `latency_p95` | 95th percentile latency over 20 burst requests | Pipeline latency scales multiplicatively with step count |
| **Performance** | `rate_limit` | 429 + Retry-After on burst of 50 at 20 req/s | Agents flood endpoints without a backoff signal |

### 4.1 Scoring Function

For a set of check results R = {r₁, r₂, ..., r₈}, the weighted score W is:

```
W = (avg_security × 0.30) + (avg_reliability × 0.40) + (avg_performance × 0.30)
```

where `avg_category` is the mean of all check scores in that category (0–100).

The security cap rule applies when any security check scores 0:

```
W_final = min(W, 59.0)  if  ∃ rᵢ: rᵢ.category = "security" ∧ rᵢ.score = 0
         W              otherwise
```

This formulation ensures that a catastrophic security failure (score=0) caps the
grade at D regardless of other scores, preventing the weighted average from
obscuring a binary failure. See ADR-02 for full justification.

---

## 5. The Ground Truth Database Methodology

### 5.1 The External Ground Truth Problem

The fundamental challenge in evaluating AI agent behavior is the absence of a
ground truth oracle. For interface reliability (Section 4), this problem is
tractable: the check algorithms are deterministic and the ground truth is the
server's observed behavior. But for the higher-level question — *"did this AI
agent make the correct decision?"* — no deterministic oracle exists.

The AI evaluation literature has addressed this through proxy metrics: human
preference labels (Christiano et al., 2017), red-teaming (Ganguli et al., 2022),
and model-based scoring (Zheng et al., 2023). Each approach has a known limitation:
preference labels are not correctness labels; red-teaming identifies failure modes
but not correctness rates; model-based scoring is circular.

Fynor's Ground Truth Database methodology provides a different approach: **domain
expert annotation of real agent decisions in production deployments.**

### 5.2 Methodology

The Ground Truth Database is constructed through the following process:

**Step 1: Decision logging.** Every AI agent decision in a client deployment is
captured by the Fynor runtime monitor (`decision_logger.py`). A decision log entry
contains: the agent's input, the agent's decision, the domain context, the
timestamp, and the deployment configuration.

**Step 2: Ontology checking.** The domain ontology (`.ontology.json`) defines
the correct behavior for each decision type in the domain (e.g., "an AI trading
agent recommending a leveraged position > 3× must require human approval"). The
runtime monitor flags decisions that violate the ontology.

**Step 3: Expert annotation.** Flagged decisions enter a review queue. A domain
expert (FINRA compliance officer, clinical pharmacist, legal counsel — domain-
specific) reviews each decision and labels it CORRECT or INCORRECT with a
written rationale.

**Step 4: Ground truth record creation.** The labeled decision, expert rationale,
and ontology rule reference are written to the ground truth database as an
immutable record.

**Step 5: Ontology update (Junction 3).** When a pattern of INCORRECT decisions
is observed, the Ontology Update Agent (Junction 3) proposes a new or modified
ontology rule. The domain expert approves or rejects the proposal.

### 5.3 Properties of the Resulting Dataset

The Ground Truth Database has several properties that distinguish it from
existing AI evaluation datasets:

**Production provenance:** Every record comes from a real deployment decision,
not a constructed benchmark. This eliminates the construct validity question
(does the benchmark measure what the real system does?) by construction.

**Domain specificity:** Records are labeled by domain experts with operational
accountability — not crowdworkers. The label quality is bounded by domain expert
competence rather than annotator agreement.

**Compound value:** Each new deployment adds records. Each record improves the
ontology. An improved ontology detects more violations. More detected violations
generate more records. This is a data flywheel.

**Non-replicability:** A competitor cannot replicate this database without:
(a) deploying Fynor or an equivalent in live enterprise environments, and
(b) recruiting domain experts to label decisions over multiple years.

### 5.4 Growth Projection and Defensibility Threshold

Based on projected client deployments:
- 5,000 records: sufficient for reliable Junction 3 proposals (sufficient sample size per domain rule)
- 10,000 records: defensible as a publishable benchmark dataset
- 50,000 records: sufficient coverage for a domain ontology standard (Company Brain)

At the projected rate of 500 records/month from Year 3 of Phase C deployments,
the 10,000-record defensibility threshold is reached in approximately 20 months
of Phase C operation.

---

## 6. Evaluation Design (Future Work)

The following empirical studies are planned for the v1.0 release (Month 20):

### Study 1: Check Accuracy on Real MCP Servers

**Design:** Run all 8 checks against N=50 publicly accessible MCP servers.
Manually inspect each server to establish a ground truth label for each check
(pass/fail). Compute precision, recall, and F1 for each check.

**Hypothesis:** Each check achieves precision ≥ 0.85 and recall ≥ 0.80.

**Success criterion:** Any check below P=0.75 is redesigned before v1.0 ships.

### Study 2: Score Reproducibility

**Design:** Run all 8 checks against N=20 MCP servers, 5 times each, at 1-hour
intervals. Compute the within-server score variance for each check.

**Hypothesis:** Score variance for deterministic checks (schema, retry, auth_token,
rate_limit, timeout) = 0. Score variance for probabilistic checks (latency_p95,
error_rate) within the documented ε bounds.

### Study 3: Certification Validity

**Design:** For N=10 MCP servers that held Agent-Ready certification for ≥60 days,
retrospectively examine whether those servers experienced production AI pipeline
failures during the certification period. Compare to a matched set of N=10
uncertified servers.

**Hypothesis:** Certified servers experience statistically fewer AI pipeline
failures (two-sample Fisher's exact test, α=0.05).

---

## 7. The Meta-Evaluation Problem

**Who evaluates the evaluator?**

This is the most important open question in the Fynor framework. If Fynor grades
an MCP server as B (81.5/100) and the server then causes a catastrophic AI pipeline
failure, what does that tell us?

Three possible interpretations:
1. The failure was in a failure mode not covered by the 8 checks (taxonomy gap)
2. The server's behavior changed after certification (temporal validity gap)
3. The check correctly identified a risk (score was not A) but the operator
   chose to deploy anyway (deployment decision gap)

Interpretation 1 is addressed by the self-learning loop: Junction 2 can propose
new checks from observed failures. Interpretation 2 is addressed by scheduled
re-checking (daily for certified servers). Interpretation 3 is outside the
technical scope of the framework — it is a governance decision.

The meta-evaluation methodology is documented in full in `docs/research/meta-evaluation.md`.

---

## 8. Limitations

**Check coverage:** The eight checks cover the most common agent-specific failure
modes but do not cover all possible failure modes. The taxonomy is a starting point,
not a complete specification.

**Temporal validity:** Check results represent the server's state at the time of
measurement. A server can change behavior after certification. The 30-day certification
window and daily re-check requirement mitigate but do not eliminate this risk.

**Target accessibility:** Checks require network access to the target. Servers
behind VPNs, IP whitelists, or private networks cannot be checked from Fynor's
hosted infrastructure. CLI mode (local execution) is required for these cases.

**MCP v0.1 scope:** Version 0.1 implements checks for MCP servers only. The
taxonomy is designed to generalize to other interface types (v0.2 through v1.0),
but the empirical validation in Section 6 is MCP-specific.

---

## 9. Ethical Considerations

**Consent for check runs:** Fynor's Terms of Service require users to have
authorization to check any target. Automated checks against third-party servers
without consent are prohibited.

**Certification liability:** Agent-Ready certification is an opinion about
observed interface behavior, not a warranty of future behavior or safety. The
certificate explicitly disclaims warranty. Fynor does not accept liability for
failures of certified servers.

**Ground truth database ethics:** Phase C decision logs may contain sensitive
information (trading decisions, patient data, legal analysis). All such data
is encrypted with per-client keys, with no Fynor operator access. Domain expert
reviewers are bound by client confidentiality agreements.

**Impact of false certification:** An incorrectly certified server (false positive)
may cause developers to trust an unreliable interface for production AI agents.
This is mitigated by the 30-day certification window, daily re-checking, and the
immediate suspension policy on any failing check.

---

## 10. Future Work

- **Study 1–3 execution** (Month 18–20): Empirical validation of check accuracy,
  reproducibility, and certification validity
- **Taxonomy extension** (v0.2–v1.0): REST, GraphQL, WebSocket, gRPC, SOAP, CLI
  checks extending the same three-category framework
- **Multi-modal checks** (v2.0): Checks for AI agents that interact with image,
  audio, or video interfaces — where the failure modes differ from text-based APIs
- **Federated ground truth** (Phase D): Inter-organizational sharing of
  non-identifying ontology rules across Company Brain subscribers
- **Public benchmark dataset** (Month 24): Release of anonymized check results
  across 100+ MCP servers as an open research dataset

---

## References

Agrawal, R., & Srikant, R. (1994). Fast algorithms for mining association rules in large databases. *VLDB*, 487-499.

Anthropic. (2024). *Model Context Protocol specification*. https://spec.modelcontextprotocol.io/

Basiri, A., Jiang, N., Kong, W., Poblete, P., Kehoe, T., Bhagwan, R., ... & Tseitlin, A. (2016). Chaos engineering. *IEEE Software*, 33(3), 35-41.

Beyer, B., Jones, C., Petoff, J., & Murphy, N.R. (2016). *Site Reliability Engineering: How Google Runs Production Systems*. O'Reilly Media.

Bowman, S.R. (2023). Eight things to know about large language models. *arXiv:2304.00612*.

Christiano, P., Leike, J., Brown, T.B., Martic, M., Legg, S., & Amodei, D. (2017). Deep reinforcement learning from human preferences. *NeurIPS*.

Ganguli, D., Lovitt, L., Kernion, J., Askell, A., Bai, Y., Kadavath, S., ... & Clark, J. (2022). Red teaming language models to reduce harms. *arXiv:2209.07858*.

Humble, J., & Farley, D. (2010). *Continuous Delivery: Reliable Software Releases Through Build, Test, and Deployment Automation*. Addison-Wesley.

Lamport, L., Shostak, R., & Pease, M. (1982). The Byzantine generals problem. *ACM Transactions on Programming Languages and Systems*, 4(3), 382-401.

Liang, P., Bommasani, R., Lee, T., Tsipras, D., Soylu, D., Yasunaga, M., ... & Leskovec, J. (2022). Holistic evaluation of language models. *arXiv:2211.09110*.

Monarch, R. (2021). *Human-in-the-Loop Machine Learning*. Manning Publications.

Montgomery, D.C. (2009). *Introduction to Statistical Quality Control*, 6th ed. Wiley.

Nygard, M.T. (2007). *Release It!: Design and Deploy Production-Ready Software*. Pragmatic Bookshelf.

Page, E.S. (1954). Continuous inspection schemes. *Biometrika*, 41(1/2), 100-115.

Panickssery, A., Bowman, S.R., Feng, S., Bao, F., Budhiraja, A., Callison-Burch, C., ... & Zettlemoyer, L. (2024). LLM evaluators recognize and favor their own generations. *arXiv:2404.13076*.

Ross, R., McEvilley, M., & Oren, J.C. (2016). *Systems Security Engineering: Considerations for a Multidisciplinary Approach in the Engineering of Trustworthy Secure Systems*. NIST Special Publication 800-160.

Settles, B. (2012). *Active Learning*. Morgan & Claypool Publishers.

Shewhart, W.A. (1931). *Economic Control of Quality of Manufactured Product*. Van Nostrand.

Zheng, L., Chiang, W.L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., ... & Stoica, I. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. *NeurIPS*.

Zanzotto, F.M. (2019). Human-in-the-loop artificial intelligence. *Journal of Artificial Intelligence Research*, 64, 243-252.
