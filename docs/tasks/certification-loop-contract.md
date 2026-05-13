# Certification Loop Contract

**SDD Layer:** Task  
**Governs:** `fynor/certification/`, `infrastructure/lambdas/cert_evaluator.py`  
**Design source:** `docs/sla.md`, `docs/deployment-architecture.md`  
**Status:** Active — Month 6  
**Last updated:** 2026-05-13

This document defines the implementation contract for the 30-day Agent-Ready
certification loop. Do not implement this before Month 6 (see `docs/tasks/build-sequence.md`).

**Decision basis:** D8 (DynamoDB TTL + EventBridge daily cron, not a counter,
not Postgres).

---

## Why Not a Counter

The simplest implementation — a `consecutive_passing_days` counter on the
target record — fails the SLA requirements in `docs/sla.md`:

> "A FYNOR_INFRA_ERROR event (Fynor's own infrastructure failing) shall not
> count as a failing day toward certification suspension."

A counter cannot distinguish "failed because the target server was broken"
from "failed because Fynor's own Lambda/DynamoDB was down." The counter
resets on any failure, including Fynor's own outages.

The correct implementation stores one record per (target, date) and marks
each record with the failure cause. The 30-day window query then excludes
`fynor_infra_err = True` days from the pass/fail evaluation.

---

## Data Model

### `fynor-daily-results` DynamoDB Table (defined in api-implementation-contract.md)

One record per (target_hash, date):

```
{
    "target_hash": "sha256_of_url",   # PK
    "date": "2026-05-13",             # SK (YYYY-MM-DD)
    "passed": true,                   # Did the best run of the day pass?
    "grade": "A",                     # Best grade achieved this day
    "fynor_infra_err": false,         # Was failure caused by Fynor infra?
    "runs_count": 3,                  # How many check runs happened this day
    "best_weighted_score": 92.5,
    "TTL": 1752537600                 # Unix timestamp: now + 45 days
}
```

**Write path:** After every check run completes (orchestrator Lambda), a
`DailyResultWriter` Lambda upserts this record for today's date. If a record
already exists for today: update only if the new run's grade is better
(keep best-of-day).

---

## EventBridge Cron

**Schedule:** `cron(0 2 * * ? *)` — runs at 02:00 UTC every day  
**Target:** `CertEvaluatorLambda`

The cron fires once per day and evaluates ALL registered targets. It does not
evaluate individual targets on-demand.

```python
# infrastructure/lambdas/cert_evaluator.py

def handler(event: dict, context: Any) -> dict:
    """
    Triggered by EventBridge at 02:00 UTC daily.
    For every registered target:
      1. Query last 30 days from fynor-daily-results
      2. Evaluate: pass or suspend?
      3. Update fynor-certifications table
      4. Trigger cert.issued / cert.suspended webhooks if status changed
    """
```

---

## Certification Evaluation Logic

```python
# fynor/certification/evaluator.py

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

CERTIFICATION_WINDOW_DAYS = 30  # locked — do not make configurable
MIN_RUNS_PER_DAY = 1            # at least one check run must exist per day

CertVerdict = Literal["CERTIFIED", "PENDING", "SUSPENDED"]

@dataclass
class DayRecord:
    date: date
    passed: bool
    fynor_infra_err: bool
    runs_count: int

def evaluate_certification_window(
    records: list[DayRecord],
    today: date,
) -> tuple[CertVerdict, int]:
    """
    Returns (verdict, qualifying_days_count).

    Rules:
    1. Look at the last 30 calendar days (today - 29 days through today)
    2. For each day in the window:
       - If no record exists: the day counts as a FAIL (server not monitored)
       - If fynor_infra_err == True: the day is EXCLUDED from evaluation
         (neither pass nor fail — shrinks the effective window)
       - If passed == True: counts as a passing day
       - If passed == False: counts as a failing day → SUSPENDED immediately
    3. If all non-excluded days pass AND qualifying_days >= 30: CERTIFIED
    4. If all non-excluded days pass AND qualifying_days < 30: PENDING
    5. If any non-excluded day fails: SUSPENDED

    The effective window may be > 30 days if infra errors excluded some days.
    Keep expanding the lookback window (max 60 days) until 30 qualifying days
    are found or a fail is encountered.
    """
    window_start = today - timedelta(days=29)
    record_map = {r.date: r for r in records}

    qualifying_days = 0
    lookback_days = 0
    current_date = today

    while qualifying_days < CERTIFICATION_WINDOW_DAYS and lookback_days < 60:
        record = record_map.get(current_date)

        if record is None:
            # Day not monitored — counts as fail only if within first 30 days
            if lookback_days < 30:
                return "SUSPENDED", qualifying_days
        elif record.fynor_infra_err:
            # Excluded day — don't count, don't fail
            pass
        elif not record.passed:
            return "SUSPENDED", qualifying_days
        else:
            qualifying_days += 1

        current_date -= timedelta(days=1)
        lookback_days += 1

    if qualifying_days >= CERTIFICATION_WINDOW_DAYS:
        return "CERTIFIED", qualifying_days
    else:
        return "PENDING", qualifying_days
```

**Verifiable by:**
```bash
pytest tests/certification/test_evaluator.py -v
# Must cover ALL of these cases:
#   - 30 consecutive passing days → CERTIFIED
#   - 29 passing + 1 infra error → PENDING (only 29 qualifying)
#   - 29 passing + 1 infra error + 1 more passing → CERTIFIED (31 lookback, 30 qualifying)
#   - 1 failing day anywhere → SUSPENDED
#   - No records for 5 days → SUSPENDED (unmonitored days count as fail)
#   - All infra errors (60 days) → PENDING (never certified without real passing days)
```

---

## Certificate Issuance

When verdict changes to CERTIFIED for the first time:

```python
@dataclass
class Certificate:
    cert_id: str              # UUID v4, generated on first issuance
    target_url: str
    grade: str                # Grade at time of certification
    issued_at: datetime       # When CERTIFIED first achieved
    valid_until: datetime     # issued_at + 365 days (one year)
    badge_url: str            # CloudFront SVG URL
    cert_status: str          # "CERTIFIED"
```

**Badge URL format:** `https://badge.fynor.tech/{cert_id}.svg`

When verdict changes from CERTIFIED to SUSPENDED:
- `cert_status` → `"SUSPENDED"`
- `valid_until` is NOT changed (historical record preserved)
- Badge SVG changes to show "Suspended" state
- `cert.suspended` webhook fires

When a suspended cert re-achieves CERTIFIED:
- Same `cert_id` is reused (continuity of identity)
- `issued_at` is NOT updated (preserves original issue date)
- A new `reinstated_at` field is set
- `cert.reinstated` webhook fires

---

## Badge SVG Contract

**Hosting:** CloudFront distribution, origin: S3 bucket  
**URL pattern:** `https://badge.fynor.tech/{cert_id}.svg`  
**SLA:** < 200ms globally (from `docs/sla.md`)  
**Cache TTL:** 300 seconds (5 minutes) — badges reflect suspension within 5 minutes

```
Badge states:
  CERTIFIED (Grade A): Green background, "Agent-Ready A" text
  CERTIFIED (Grade B): Blue background, "Agent-Ready B" text
  CERTIFIED (Grade C): Yellow background, "Agent-Ready C" text
  PENDING:             Grey background, "Pending Certification" text
  SUSPENDED:           Red background, "Suspended" text
  REVOKED:             Dark grey, "Revoked" text
```

**Badge generation:**
- SVG is pre-rendered and stored in S3 when cert status changes
- CloudFront serves from cache; S3 is the origin
- Never 404 — if cert_id not found, serve a "Not Found" SVG (not a 404 HTTP error)
  because a 404 breaks the GitHub README badge display

**Verifiable by:**
```bash
pytest tests/certification/test_badge.py -v
# Must verify: SVG generated for each status, correct colors,
#              cache headers present, non-existent cert_id returns SVG not 404
```

---

## Webhook Events

| Event | When fired |
|-------|-----------|
| `cert.issued` | Target first achieves CERTIFIED status |
| `cert.suspended` | CERTIFIED → SUSPENDED transition |
| `cert.reinstated` | SUSPENDED → CERTIFIED transition |
| `cert.revoked` | Manual revocation (account closure, ToS violation) |

Webhook payload:
```json
{
    "event": "cert.suspended",
    "cert_id": "uuid",
    "target_url": "https://...",
    "previous_status": "CERTIFIED",
    "new_status": "SUSPENDED",
    "reason": "Failing day: 2026-05-13, grade D",
    "timestamp": "2026-05-14T02:05:33Z",
    "fynor_signature": "sha256=<hmac>"
}
```

---

## Cron Failure Handling

If the EventBridge cron Lambda fails (throws an exception):

1. Lambda retries automatically (EventBridge default: 2 retries)
2. If all retries fail: a CloudWatch alarm fires (target: Sriram's email)
3. Affected targets: their `last_evaluated_at` is not updated
4. No cert status changes happen that day (conservative — no false suspensions)
5. The next day's cron run picks up where it left off — it queries the last
   30 days of history, so one missed day does not corrupt the evaluation

**Verifiable by:**
```bash
pytest tests/certification/test_cert_cron_failure.py -v
# Must verify: failed cron does not change cert_status,
#              next successful cron evaluates correctly
```

---

## Quality Gate

```bash
pytest tests/certification/ \
  --cov=fynor/certification \
  --cov-fail-under=90 -v
# Evaluator function: 100% branch coverage required
# (every combination of pass/fail/infra_err must be tested)
```
