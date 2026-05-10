# Data Schemas — Python Dataclasses + PostgreSQL

## Python Dataclasses (fynor/checks/__init__.py)
# This is the exact code. Copy-paste ready.

```python
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"   # Blocks agent operation entirely
    HIGH     = "HIGH"       # Causes agent data corruption or auth failure
    MEDIUM   = "MEDIUM"     # Degrades agent reliability significantly
    LOW      = "LOW"        # Minor inefficiency, agent still functions


class InterfaceType(str, Enum):
    MCP       = "MCP"
    REST      = "REST"
    GRAPHQL   = "GRAPHQL"
    GRPC      = "GRPC"
    WEBSOCKET = "WEBSOCKET"
    SOAP      = "SOAP"
    CLI       = "CLI"
    SECURITY  = "SECURITY"   # cross-cutting — runs on all interface types


@dataclass
class CheckResult:
    check_id:       str             # "MCP_001", "REST_003", "SEC_002"
    interface_type: InterfaceType   # which protocol bucket
    name:           str             # "Response Time P95"
    score:          int             # 0-100
    passed:         bool
    severity:       Severity        # ADR-01: field, NOT embedded in failure_code string
    failure_code:   str | None      # "MCP_001_HIGH_LATENCY" or None if passed
    remediation:    str | None      # specific fix string or None if passed
    metadata:       dict = field(default_factory=dict)  # raw check data


@dataclass
class AuditResult:
    audit_id:       str
    url:            str
    interface_type: InterfaceType
    score:          int             # 0-100 weighted final score
    grade:          str             # A / B / C / D / F
    results:        list[CheckResult]
    created_at:     str             # ISO 8601 timestamp
    report_url:     str | None      # scorecard.fynor.dev/r/{audit_id}
```

## Score Aggregator Logic (scorer.py)
# Exact logic — implement this in fynor/scorer.py

```python
BUCKET_WEIGHTS = {
    "security":    0.30,
    "reliability": 0.40,
    "performance": 0.30,
}

SEVERITY_MULTIPLIER = {
    Severity.CRITICAL: 0.0,   # Zero score — hard fail
    Severity.HIGH:     0.4,   # 40% of score carries through
    Severity.MEDIUM:   0.7,   # 70% of score carries through
    Severity.LOW:      1.0,   # Full score, minor issue
}

GRADE_BOUNDARIES = [
    (90, "A"),   # Agent-ready
    (75, "B"),   # Minor issues, usable
    (60, "C"),   # Reliability concerns
    (45, "D"),   # Not recommended for production agents
    (0,  "F"),   # Do not connect any agent to this
]

# HARD RULE: CRITICAL security failure -> cap entire audit at grade D
# Check for this BEFORE computing weighted score
```

## PostgreSQL Tables — Phase B (Month 9, exact SQL)

```sql
-- Enterprise clients table
CREATE TABLE clients (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL,
    tier       TEXT NOT NULL CHECK (tier IN ('free','managed','enterprise','enterprise_plus')),
    domain     TEXT,                    -- 'fintech_trading', 'healthcare_clinical', NULL for generic
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Every audit run ever
CREATE TABLE audit_sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id      UUID REFERENCES clients(id),   -- NULL for free tier
    url            TEXT NOT NULL,
    interface_type TEXT NOT NULL,
    domain         TEXT,                           -- NULL for non-Phase-C audits
    score          INTEGER,
    grade          CHAR(1),
    report_url     TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    completed_at   TIMESTAMPTZ
);

-- Every individual check result
CREATE TABLE check_results (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id       UUID REFERENCES audit_sessions(id) ON DELETE CASCADE,
    client_id      UUID REFERENCES clients(id),   -- for RLS
    check_id       TEXT NOT NULL,                  -- "MCP_001"
    interface_type TEXT NOT NULL,
    name           TEXT NOT NULL,
    score          INTEGER NOT NULL,
    passed         BOOLEAN NOT NULL,
    severity       TEXT NOT NULL,
    failure_code   TEXT,
    remediation    TEXT,
    metadata       JSONB DEFAULT '{}',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Aggregated failure patterns (updated by weekly batch job)
CREATE TABLE failure_patterns (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_id       TEXT NOT NULL,
    interface_type TEXT NOT NULL,
    failure_rate   NUMERIC(5,2),    -- percentage that fail this check
    sample_count   INTEGER,
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);
```

## PostgreSQL Tables — Phase C (Month 15+, exact SQL)

```sql
-- Domain ontology rules (Fynor's proprietary IP — private repo)
CREATE TABLE domain_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id         TEXT UNIQUE NOT NULL,            -- "rule-0042"
    domain          TEXT NOT NULL,                   -- "fintech_trading_compliance"
    description     TEXT NOT NULL,
    condition       TEXT NOT NULL,
    expected_action TEXT NOT NULL,
    failure_mode    TEXT NOT NULL,
    severity        TEXT NOT NULL,
    version         INTEGER DEFAULT 1,
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Ground truth labels — THE PRIMARY MOAT
CREATE TABLE ground_truth_labels (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id        UUID REFERENCES clients(id),
    domain           TEXT NOT NULL,
    rule_id          TEXT REFERENCES domain_rules(rule_id),
    agent_input      JSONB NOT NULL,
    agent_decision   TEXT NOT NULL,
    verdict          TEXT NOT NULL CHECK (verdict IN ('CORRECT','INCORRECT')),
    correct_decision TEXT,                           -- only when verdict = INCORRECT
    auditor          TEXT NOT NULL,                  -- domain expert identifier
    audit_date       DATE NOT NULL,
    jurisdiction     TEXT,                           -- "US", "EU", "UK" for compliance
    embedding        vector(1536),                   -- pgvector for similarity search
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

## Row-Level Security — Phase B to Phase C Migration (ADR-04)

```sql
-- Phase B: Enable RLS on all sensitive tables
ALTER TABLE audit_sessions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE check_results       ENABLE ROW LEVEL SECURITY;
ALTER TABLE ground_truth_labels ENABLE ROW LEVEL SECURITY;

-- Policy: each client sees only their own data
CREATE POLICY client_isolation ON audit_sessions
    USING (client_id = current_setting('app.current_client_id')::UUID);

CREATE POLICY client_isolation ON check_results
    USING (client_id = current_setting('app.current_client_id')::UUID);

CREATE POLICY client_isolation ON ground_truth_labels
    USING (client_id = current_setting('app.current_client_id')::UUID);

-- Phase C migration to per-DB (when enterprise client demands full isolation):
-- Step 1: Provision dedicated AWS RDS instance for that client
-- Step 2: Migrate their rows: SELECT * FROM audit_sessions WHERE client_id = 'X'
-- Step 3: Update connection string in their config
-- Step 4: DROP their rows from shared DB
-- Step 5: Verify client can access new DB with no data loss
-- RLS -> per-DB migration path is clean and reversible
```

## Ground Truth Record Schema (Phase C moat — JSON)

```json
{
  "record_id": "gt-2027-001",
  "domain": "fintech_trading_compliance",
  "jurisdiction": "US",
  "rule": "flag_transactions_above_threshold",
  "threshold_usd": 50000,
  "agent_input": "{ trade: { amount: 75000, counterparty: 'Acme Corp' } }",
  "agent_decision": "approved_without_flag",
  "verdict": "INCORRECT",
  "correct_decision": "should_have_flagged",
  "auditor": "domain_expert_1",
  "audit_date": "2027-03-01",
  "client_id": "client_anonymized_001"
}
```

Growth math:
- Year 3 (2029): 10 clients x 50 decisions/month = 500 records/month
- Year 4 (2030): 25 clients -> 1,250 records/month
- Year 5+: 50+ clients -> 2,500+ records/month (compound advantage)
- Moat becomes defensible at ~10,000+ records (estimated late 2030)

## Domain Ontology Rule Schema (Phase C — JSON)

```json
{
  "domain": "fintech_trading_compliance",
  "rule_id": "rule-0042",
  "description": "Trading AI agent must flag any transaction above reporting threshold",
  "condition": "transaction.amount > reporting_threshold_usd",
  "expected_action": "GENERATE_FLAG",
  "failure_mode": "SILENT_APPROVAL",
  "severity": "CRITICAL"
}
```

Ontology storage:
- Private Git repo: ontologies/ folder in fynor-mcp-scorecard (private branch) or separate private repo
- Version control: every rule addition = one commit with change rationale message
- Phase C launch: ontologies/fintech_trading.json with 20-50 rules
- Year 3 target: 200-500 rules across 2-3 verticals

Built from:
- Domain expert interviews (compliance officers, risk managers)
- Regulatory documents (FINRA, SEC rules; HIPAA for healthcare)
- Real-world failures observed in Phase A/B client engagements
- Princeton AI Reliability Definition (February 2026)

## Metadata Field Examples (per check type)

MCP_001 metadata: { "p95_ms": 2847, "p50_ms": 1234, "sample_count": 20, "max_ms": 5100 }
REST_002 metadata: { "burst_rate": 100, "got_429": false, "requests_sent": 100 }
SEC_001 metadata: { "leaked_header": "X-Auth-Token", "token_prefix": "sk-" }
GRPC_001 metadata: { "field_removed": "user_id", "old_type": "string", "breaking": true }
CLI_001 metadata: { "command": "mycli --bad-flag", "exit_code": 0, "stderr": "Error: unknown flag" }
