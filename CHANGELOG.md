# Changelog

All notable changes to Fynor are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- `fynor/interpretation.py` — deterministic trust layer for all 11 checks. For every check
  and every score band (pass / degraded / fail / na) this module provides: (1) **business
  impact** — why the finding matters for AI agent operators, in plain English; (2) **remediation**
  — numbered steps to fix the issue; (3) **reproduce** — the exact curl command the client
  can run themselves to verify the finding; (4) **refs** — relevant OWASP, RFC, and Fynor
  docs links. Fully deterministic — no AI API dependency, zero latency cost. Serves as the
  structured foundation for AI Junction 1 (Month 7).
- CLI `fynor check` now displays a FINDINGS section below the scorecard for every failing
  check, showing: WHAT WE MEASURED, BUSINESS IMPACT FOR YOUR AI AGENTS, HOW TO FIX,
  REPRODUCE IT YOURSELF, and REFERENCES. The reproduce command substitutes the actual
  target URL automatically.
- JSON output (`--output json`) now includes `impact`, `remediation`, `reproduce`, and `refs`
  fields per check result — enabling programmatic consumption by CI/CD pipelines, dashboards,
  and the hosted API.
- `tests/test_interpretation.py` — 112 tests enforcing coverage (every check has pass/fail/na
  interpretations), content quality (non-empty, AI-agent-focused), and structural correctness.

### Fixed
- `find_timestamp` false-positive: substring matching caused `events_url`, `status`, and similar
  field names to be misidentified as timestamp fields because they contain a timestamp keyword
  (e.g. "ts") as a substring. Switched to word-boundary semantics: a key matches only when its
  lowercase form is in `_TIMESTAMP_KEYS` exactly, or when an underscore-separated segment of
  the lowercase key is in `_TIMESTAMP_KEYS`. Added 8 regression tests covering the GitHub API
  response shape that triggered the bug. (`fynor/checks/shared.py`)
- REST N/A gap: `schema`, `retry`, and `tool_description_quality` are JSON-RPC 2.0 checks that
  do not apply to REST, GraphQL, or gRPC targets. Previously they scored 0 (FAIL), which
  inflated failure counts and depressed grades for non-MCP targets. They are now marked
  `result="na"` for non-MCP interface types and excluded from scoring and the failure summary.
  CLI display shows `- N/A` instead of `✗   0` for these checks. (`fynor/cli.py`,
  `fynor/scorer.py`)
- API dispatch parity: `_dispatch_checks` in the hosted API only ran the original 8 checks,
  silently omitting `data_freshness`, `tool_description_quality`, and `response_determinism`
  added in v0.2. The API and CLI now produce identical 11-check scorecards. (`fynor/api/main.py`)
- `apply_profile` N/A preservation: when a profile threshold existed for a check that was
  already marked `result="na"` (e.g. `tool_description_quality` under the security profile on
  a REST target), the rebuilt `CheckResult` dropped the `result` field, causing the N/A check
  to silently re-enter scoring as a 0-score failure. Fixed by passing `result=r.result` in the
  constructor. Added 17 profile unit tests (`tests/test_profiles.py`). (`fynor/profiles.py`)

---

## [0.2.0-dev] — 2026-05-14

### Added
- Check #9: `data_freshness` — detects stale response data via timestamp field analysis
- Check #10: `tool_description_quality` — validates tool descriptions for AI model selectability
- Check #11: `response_determinism` — verifies 3-probe structural schema consistency
- `fynor/profiles.py` — `CheckProfile` with `apply_profile()` and 3 built-in profiles:
  `default`, `security` (stricter: ≤1% error, ≤500ms P95, ≤60min data, full determinism),
  `financial` (SOC 2 / PCI DSS optimised)
- `--profile` flag on `fynor check` command: `fynor check --profile security <url>`

### Changed
- `auth_token` check: added F4 (invalid Bearer token accepted) as a fourth failure condition
- `fynor/checks/mcp/__init__.py`: exports 11 checks + updated `ALL_CHECKS` list
- `fynor/scorer.py`: `_CHECK_CATEGORY` updated for checks 9–11 (all → reliability)
- `docs/adr/ADR-03`: Amendment 1 — taxonomy entries for checks 9–11 + auth_token F4
- `docs/adr/ADR-04`: Amendment 1 — threshold justifications for new scoring bands
- `docs/tasks/check-implementation-contract.md`: contracts for checks 9–11 + auth_token F4
- `docs/tasks/build-sequence.md`: Month 1 deliverables updated to 11 checks + profiles
- `README.md`: updated to 11 checks, check table expanded, --profile example added

---

### Planned for v0.1.0 (Month 6)
- Live end-to-end `fynor check` run against a real MCP server
- AI Junction 1: Failure Interpretation Agent (Month 7)
- GitHub Action `fynor/check@v1` (Month 8)

---

## [0.1.0-dev] — 2026-05-13

### Added
- `fynor/history.py` — append-only JSONL check history log
- `fynor/scorer.py` — ADR-02 locked scoring engine (Security 30% + Reliability 40% + Performance 30%)
- `fynor/adapters/base.py` — BaseAdapter abstract class
- `fynor/adapters/mcp.py` — MCPAdapter (JSON-RPC 2.0, v0.1)
- `fynor/adapters/rest.py` — RESTAdapter stub (v0.2, Month 9)
- All 8 MCP checks: `latency_p95`, `error_rate`, `schema`, `retry`, `auth_token`, `rate_limit`, `timeout`, `log_completeness`
- `fynor/intelligence/pattern_detector.py` — 3-algorithm statistical engine (co-failure, drift, time signature)
- `fynor/intelligence/failure_interpreter.py` — AI Junction 1 stub (Month 7)
- `fynor/intelligence/pattern_learner.py` — AI Junction 2 stub (Month 9)
- `fynor/intelligence/ontology_updater.py` — AI Junction 3 stub (Month 18)
- `fynor/certification/certificate.py` — Agent-Ready Certificate data model
- `fynor/monitoring/decision_logger.py` — Phase C AI OS decision recorder
- `fynor/brain/schema.py` — Phase D Company Brain OntologyFile standard
- `fynor/cli.py` — `fynor check`, `fynor history`, `fynor patterns` commands
- `tests/test_scorer.py` — 5 scorer unit tests
- `tests/test_history.py` — 5 history unit tests
- `docs/adr/` — Architecture Decision Records (ADR-01 through ADR-04)
- `docs/business/` — Financial model, market sizing, competitive moat analysis
- `docs/research/` — Academic research paper and meta-evaluation methodology
- `docs/deployment-architecture.md` — Production infrastructure design
- `docs/api-specification.md` — Hosted service REST API specification
- `docs/sla.md` — Service Level Agreement for certification badge system
- `docs/risk-register.md` — Risk register
- `docs/privacy-data-handling.md` — Data handling and privacy specification

### Fixed
- `pyproject.toml`: replaced `setuptools.backends.legacy:build` (requires setuptools ≥68.2) with `setuptools.build_meta` for universal compatibility
- `tests/test_scorer.py`: removed stale `CertificationStatus` import that caused collection-time `ImportError`

---

## [0.0.1] — 2026-05-08

### Added
- Initial repository structure
- Three-layer architecture scaffold: Software for Agents / AI OS / Company Brain
- `README.md` with complete platform narrative
