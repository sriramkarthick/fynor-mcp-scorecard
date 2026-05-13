# Changelog

All notable changes to Fynor are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
