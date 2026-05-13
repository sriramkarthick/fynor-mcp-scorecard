# Fynor Service Level Agreement

**Effective date:** Month 12 (hosted service launch)  
**Applies to:** Pro, Team, and Enterprise plans

---

## Badge Endpoint SLA — 99.9% Uptime

The Agent-Ready badge endpoints (`fynor.tech/badge/*` and `fynor.tech/cert/*`) are
held to a **higher standard than the check API** because they are embedded in external
README files and CI pipelines. A broken badge is visible to every person who visits
a GitHub repository.

| Endpoint | Uptime SLA | Response Time SLA |
|----------|-----------|-------------------|
| `GET /badge/{cert_id}.svg` | 99.9%/month | < 200ms globally (p95) |
| `GET /cert/{cert_id}.json` | 99.9%/month | < 500ms globally (p95) |

**99.9% uptime = 43.8 minutes allowable downtime per month.**

Implementation: CloudFront + S3 static delivery. Badge SVGs are pre-rendered and
cached globally. No database calls on badge serving — zero single-point-of-failure.

---

## Check API SLA — 99.5% Uptime

| Service | Uptime SLA | Response Time SLA |
|---------|-----------|-------------------|
| `POST /api/v1/check` | 99.5%/month | < 5 minutes per check run (p95) |
| `GET /api/v1/history` | 99.5%/month | < 1s (p95) |
| `GET /api/v1/patterns` | 99.5%/month | < 1s (p95) |

**99.5% uptime = 3.6 hours allowable downtime per month.**

Check runs are the most resource-intensive operation. The 5-minute SLA allows for
the full 8-check suite including the 50-request rate_limit burst.

---

## Scheduled Checks

For Pro+ accounts with scheduled checks enabled:

| Frequency | Delivery SLA |
|-----------|-------------|
| Daily | Check completed within 2 hours of scheduled time |
| Weekly | Check completed within 4 hours of scheduled time |

If a scheduled check misses its window, Fynor retries once and notifies via email.
Missed scheduled checks do not count toward downtime calculations.

---

## Certification Continuity Guarantee

**The Agent-Ready certification status is never changed without evidence.**

- Certification is only **suspended** when a check run produces a failing result
- Certification is never suspended due to Fynor infrastructure failures
- If a check run fails due to a Fynor-side error (not a server error), the run is
  retried up to 3 times before any certification action is taken
- `FYNOR_INFRA_ERROR` events do not count toward consecutive failing days

This guarantee protects certificate holders from Fynor's own reliability issues
affecting their certification status.

---

## Scheduled Maintenance

- Maintenance windows: Sundays 02:00–04:00 UTC
- Advance notice: 72 hours for planned maintenance
- Emergency maintenance: best-effort notification
- Badge endpoints are not taken offline during maintenance

---

## Credits for SLA Violations

If monthly uptime falls below the SLA:

| Uptime | Credit |
|--------|--------|
| 99.0% – 99.5% | 10% of monthly fee |
| 95.0% – 99.0% | 25% of monthly fee |
| < 95.0% | 50% of monthly fee |

Credits are applied to the next invoice. Credits are the sole remedy for SLA violations.

---

## Exclusions

The SLA does not apply to:

- Downtime caused by the target server being unavailable (Fynor cannot guarantee
  a server's availability during its own check runs)
- Force majeure events (AWS outages affecting entire regions)
- Planned maintenance windows
- Beta features (labeled as "beta" in the dashboard)

---

## Uptime Monitoring

Public status page: `https://status.fynor.tech`  
Historical uptime: published monthly in the changelog.
