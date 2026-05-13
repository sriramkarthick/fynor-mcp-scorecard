# Fynor — Privacy and Data Handling Specification

**Last updated:** 2026-05-13  
**Applies to:** fynor.tech hosted service

---

## Data Categories

Fynor processes three categories of data with different handling requirements:

| Category | Examples | Sensitivity | Retention |
|----------|---------|-------------|-----------|
| **Check telemetry** | Request latencies, error rates, scores | Low — operational data | 90 days (Pro), 365 days (Enterprise) |
| **Target metadata** | Target URLs, interface types, API keys | Medium — operational credentials | Lifetime of account |
| **Decision logs** | AI agent decisions, domain expert verdicts | High — business-sensitive, potentially regulated | Client-controlled, minimum 7 years for regulated |

---

## What Fynor Collects

### During a Check Run

Fynor's check workers send HTTP requests to the target URL and record:
- Response status codes
- Response latencies (milliseconds)
- Response headers (for auth_token and rate_limit checks)
- Response body structure (for schema and retry checks — validates JSON envelope, does not store body content)

**Fynor does NOT store:**
- Full response bodies
- Request payloads beyond the standard probe payload
- Cookies or session tokens from target servers
- Any PII that may appear in response bodies

The response header inspection in `auth_token` check looks for patterns matching
`_SECRET_HEADER_PATTERNS` (e.g., `Authorization`, `X-API-Key`). If found, the
check records the **presence** of the header, not its value. Secret values are
never logged.

### Account Data

- Email address
- Hashed API key (bcrypt — raw key never stored after delivery)
- Subscription tier and billing information (Stripe handles payment data — never
  stored in Fynor's database)
- Target URLs registered to the account

---

## Phase C: Decision Log Data

Phase C (AI OS, 2027+) introduces a new data category: AI agent decision logs.

This data is fundamentally different from check telemetry:
- It contains the text of AI agent decisions
- It may contain business-sensitive information (trading decisions, patient summaries, legal analysis)
- It is subject to domain-specific regulations (FINRA, HIPAA, legal privilege)

**Data isolation architecture:**

```
Client A's decision logs → encrypted with Client A's KMS key
Client B's decision logs → encrypted with Client B's KMS key

Fynor operators: no access to raw decision content
Fynor AI Junction 3: reads encrypted logs via client-authorized Lambda role
Domain expert reviewer: accesses via time-limited presigned URL
```

**Fynor's role:** Fynor is a **data processor**, not a data controller, for
Phase C decision logs. The client (data controller) determines retention,
access permissions, and deletion policy.

---

## Data Retention

### Check History

| Plan | Retention | Deletion |
|------|-----------|---------|
| Free (CLI) | Local only, no server storage | User-controlled |
| Pro | 90 days rolling | Auto-deleted after 90 days |
| Team | 180 days rolling | Auto-deleted after 180 days |
| Enterprise | 365 days rolling | Auto-deleted after 365 days, or client-specified |

Extended retention available for Enterprise at additional cost.

### Decision Logs (Phase C)

| Requirement | Retention |
|-------------|-----------|
| Default | Client-controlled (7-year minimum recommended for regulated) |
| FINRA-regulated | 7 years (FINRA Rule 4370 requirement) |
| HIPAA-regulated | 6 years (45 CFR Part 164.530) |
| Right to erasure | Supported for non-regulated data within 30 days of request |

---

## Data Residency

| Region | Availability |
|--------|-------------|
| US East (Virginia) | Default |
| EU West (Ireland) | Enterprise clients with EU residency requirements |
| India (Mumbai) | Enterprise clients with DPDPA requirements |

Phase C decision logs can be configured to remain in a single region.

---

## GDPR Compliance

For users and clients in the European Economic Area:

- **Lawful basis:** Legitimate interest (check telemetry), contractual necessity (account data)
- **Data subject rights:** Access, rectification, deletion, portability — all supported via account dashboard or support request
- **Data Processing Agreement (DPA):** Available for Enterprise clients on request
- **Sub-processors:** AWS (compute, storage), Stripe (payments), Anthropic API (Junction 1 interpretations)
- **DPA with sub-processors:** Maintained and available on request

---

## India DPDPA (Digital Personal Data Protection Act, 2023)

Fynor is headquartered in Thiruppuvanam, Tamil Nadu, India. Compliance with
the India DPDPA is treated as a baseline requirement, not just for Indian clients.

- Consent-based processing for personal data
- Data Principal rights (access, correction, nomination) supported
- Data Fiduciary registration: target Month 18 (before first Indian Enterprise client)

---

## Security Controls

| Control | Implementation |
|---------|---------------|
| Encryption at rest | AES-256 for all DynamoDB tables and S3 buckets |
| Encryption in transit | TLS 1.3 minimum |
| API key storage | bcrypt hash (cost factor 12) — raw key never stored |
| Phase C client data | Per-client AWS KMS customer-managed keys |
| Access logging | AWS CloudTrail for all data access events |
| Vulnerability scanning | Dependabot + weekly `ruff` + `mypy` CI run |
| SOC 2 Type II | Target: Month 24 |

---

## Incident Response

Data breach notification timelines:
- GDPR: 72 hours to supervisory authority (Article 33)
- India DPDPA: 72 hours to Data Protection Board
- US state laws: Varies by state, maximum 30 days

Fynor maintains an incident response runbook at `docs/runbooks/incident-response.md`
(internal, created before hosted service launch).

---

## What Fynor Does Not Do

- Fynor does not sell check history or pattern data to third parties
- Fynor does not use client check data to train ML models without explicit opt-in
- Fynor does not share target URLs or check results with any party other than the account owner
- Fynor does not retain response body content from check runs
- Fynor does not access Phase C decision logs without client authorization
