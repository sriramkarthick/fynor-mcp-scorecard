# Product Interfaces — How Developers and Agents Use Fynor

## Interface Build Sequence (exact months)
Month 6:  CLI (fynor run) — primary, drives everything
Month 7:  Python SDK (from fynor import run)
Month 8:  GitHub Action (uses: fynor/check@v1)
Month 9:  REST API (POST /v1/audit) + hosted web UI (scorecard.fynor.dev)
Month 12: MCP Server (Fynor as agent tool) — ADR-05, polished not rushed
Month 15: Docker (docker run fynor/fynor) + npm (npx fynor) — community demand

## 1. CLI (fynor run) — Month 6

Primary interface. Everything else wraps this.

Commands:
  fynor run --url https://api.example.com --type rest
  fynor run --url https://mcp.example.com --type mcp
  fynor run --url grpc://service:443 --type grpc
  fynor run --url wss://stream.example.com --type websocket
  fynor run --url "mycli --help" --type cli
  fynor run --url X --type rest --domain fintech_trading    <- Phase C
  fynor run --url X --type mcp --format json
  fynor run --url X --type rest --format html --output report.html

Private endpoint support (v0 — no managed server needed):
  Local mode:  fynor run localhost:8080 --type mcp
               For servers running on developer's own machine
  Tunnel mode: ngrok http 8080 -> fynor run https://abc.ngrok.io --type mcp
               Temporary exposure for audit duration only
  Production private connector (AWS VPC peering, K8s service mesh): deferred to Phase C

## 2. Python SDK — Month 7

For developers using fynor as a library in their own code.

```python
from fynor import run, AuditResult, CheckResult

# Async usage
result: AuditResult = await run(
    url="https://api.example.com",
    type="rest",
    domain="fintech_trading"  # optional, Phase C
)

print(f"Grade: {result.grade}")   # "B"
print(f"Score: {result.score}")   # 78

for check in result.results:
    if not check.passed:
        print(f"{check.failure_code}: {check.remediation}")
        # "REST_001_SCHEMA_UNSTABLE: Pin schema version in API response headers"
```

## 3. GitHub Action — Month 8

For engineering teams running reliability checks in CI/CD.

```yaml
# In any project's .github/workflows/ci.yml
- uses: fynor/check@v1
  with:
    url: https://api.myproject.com
    type: rest
    fail-on-grade: C        # fail CI if grade drops below C
    domain: fintech_trading  # optional Phase C
```

Behaviour:
- Runs on every PR
- Fails CI if grade drops below threshold
- Posts check results as PR comment
- Links to full report at scorecard.fynor.dev/r/{audit_id}

## 4. REST API — Month 9 (FastAPI)

For CI/CD systems, dashboards, third-party integrations.

Endpoints:
  POST /v1/audit
    Body: { "url": "...", "type": "rest", "domain": null }
    Response: AuditResult JSON (immediately or audit_id for async poll)

  GET /v1/audit/{audit_id}
    Response: AuditResult JSON (full results when completed)

  GET /v1/audit/{audit_id}/report
    Response: full report JSON with all CheckResults

  GET /r/{audit_id}
    Response: shareable HTML report page (rendered by Vercel)
    URL: scorecard.fynor.dev/r/{audit_id}
    This is the viral growth mechanic — developers share this URL.

  GET /v1/patterns?domain=fintech_trading&limit=10
    Response: top failure patterns for a domain (from failure_patterns table)

## 5. MCP Server — Month 12 (ADR-05, polished)

Fynor itself as an MCP server. Any AI agent can call Fynor directly.

Strategic importance:
  The tool that CHECKS MCP servers IS ITSELF an MCP server.
  Claude, LangChain, CrewAI — any agent — can audit the APIs it uses autonomously.
  Fynor becomes part of every agent's self-check loop.
  Distribution multiplier: every AI agent deployment = potential Fynor user.
  No existing reliability tool does this. This is the demo that wins conferences.

5 tools exposed:

Tool 1: run_audit
  Input:  { url: string, type: string, domain?: string }
  Output: AuditResult (score, grade, results[], report_url)
  Use:    AI agent audits any API before starting a workflow that depends on it

Tool 2: get_remediation
  Input:  { failure_code: string }
  Output: specific fix string + estimated effort
  Use:    AI agent fetches fix for a known failure without calling Fynor again

Tool 3: compare_audits
  Input:  { audit_id_before: string, audit_id_after: string }
  Output: diff — what checks changed from pass to fail or vice versa
  Use:    CI/CD agent detects regression after a deployment

Tool 4: get_audit_status
  Input:  { audit_id: string }
  Output: { status: "running"|"complete"|"failed", progress: 0-100 }
  Use:    Agent polls for long-running audit completion

Tool 5: list_failure_patterns
  Input:  { domain: string, top_n?: int }
  Output: top N most common failure patterns for a vertical
  Use:    Agent learns what to watch for before starting a new workflow

## 6. Hosted Web UI (scorecard.fynor.dev) — Month 9

Primary conversion surface for organic discovery.

Flow:
  1. Developer finds Fynor on GitHub, HN, Twitter
  2. Goes to scorecard.fynor.dev
  3. Pastes their API URL, selects interface type
  4. Fynor runs all checks -> generates report
  5. Shareable URL: scorecard.fynor.dev/r/{audit_id}
  6. Developer shares URL with their team -> viral loop
  7. "Request full audit" button -> Phase C demand pipeline

"Request full audit" conversion funnel:
  -> 3-question Typeform:
     (a) What AI agent is this interface serving?
     (b) Is this in production or pre-production?
     (c) What is your biggest reliability concern?
  -> Results emailed to Sriram + added to Notion database
  -> Review within 24h
  -> Qualified (production agent, real concern):
       Reply with Calendly link for 30-min call
       Outcome: $5K manual audit proposal OR Phase A consulting retainer
  -> Unqualified:
       "Here's how to fix this with the Scorecard — no call needed"

## 7. Docker — Month 15

For enterprise teams running containerized tooling.

  docker run fynor/fynor run --url https://api.example.com --type rest
  docker run fynor/fynor run --url X --type mcp --format json > report.json

## 8. npm — Month 15

For JavaScript/Node.js developer community.

  npx fynor run --url https://api.example.com --type rest

Ships when community requests it — do not build until demand confirmed.

## Pricing Tiers

| Tier       | Price           | What It Includes                                     |
|------------|-----------------|------------------------------------------------------|
| Free       | $0              | unlimited local CLI (pip install fynor)              |
| Managed    | $49/month       | hosted checks, CI integration, report history        |
| Enterprise | $5K+ manual     | manual Phase C audit -> $50K-300K/year contract      |

Phase B pricing validation:
  First 20 managed users: "founding member" rate $29/month
  If they pay -> price confirmed.
  If not -> adjust before general launch.
  Hosting cost at 20 clients: <$5/month (Vercel free + GitHub Actions free minutes)
  Revenue at 20 x $29 = $580/month. Margin: 99%.
