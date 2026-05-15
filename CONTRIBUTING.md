# Contributing to Fynor

Thank you for your interest in contributing. This document explains how the codebase is structured, how decisions are made, and how to get a change merged.

---

## Quick Start

```bash
git clone https://github.com/sriramkarthick/fynor-reliability-platform.git
cd fynor-reliability-platform
pip install -e ".[dev]"
pytest tests/ -v
```

All 415+ tests must pass before any commit. If you add a feature, add tests for it.

---

## Repository Layout

```
fynor/
├── adapters/       One adapter per interface type (MCP, REST, …)
├── checks/mcp/     11 deterministic checks for MCP servers
├── checks/rest/    REST checks (coming Month 9)
├── intelligence/   Pattern detector + AI junction stubs
├── scorer.py       Weighted grade engine (ADR-02, weights locked)
├── history.py      Append-only JSONL log
└── cli.py          Click CLI entry point

docs/
├── adr/            Architecture Decision Records (locked constraints)
├── tasks/          Implementation contracts for each feature area
└── *.md            API spec, deployment architecture, SLA, privacy

tests/
├── checks/         One test file per check
├── api/            FastAPI endpoint tests
└── test_scorer.py  Scoring engine tests
```

---

## The ADR System

Four Architecture Decision Records govern every implementation decision.
Read them before touching any of the listed areas:

| ADR | Governs | File |
|-----|---------|------|
| ADR-01 | Which code is automation vs. AI junction | `docs/adr/ADR-01-architecture-principles.md` |
| ADR-02 | Scoring weights (30/40/30) and security cap | `docs/adr/ADR-02-scoring-weights.md` |
| ADR-03 | Exactly which checks exist and why | `docs/adr/ADR-03-check-taxonomy.md` |
| ADR-04 | Threshold values (z=2.5, 70%, 3×) and citations | `docs/adr/ADR-04-threshold-justification.md` |

**These are locked.** You cannot change a threshold, weight, or check taxonomy entry by editing the code alone. Propose an ADR amendment first (open an issue, explain the reasoning and cite evidence), get it discussed, then implement.

If you believe the spec is wrong, classify the bug before fixing:

- **Type A — spec-to-code gap:** spec is correct, code is wrong → fix the code.
- **Type B — intent-to-spec gap:** code does what spec says but spec was wrong → propose an ADR amendment, do not fix the code until the amendment is accepted.

---

## How to Add a New Check

1. **Open an issue first.** Describe the failure mode the check detects, which interface type(s) it applies to, and proposed scoring (what earns 100, 60, 0).

2. **Get a taxonomy entry.** A maintainer will add the check to `docs/adr/ADR-03-check-taxonomy.md`. No check without a taxonomy entry.

3. **Read the check contract.** `docs/tasks/check-implementation-contract.md` defines the function signature, return type, and determinism requirements.

4. **Implement the check.** New checks go in `fynor/checks/<interface_type>/<check_name>.py`. Every check must:
   - Return `CheckResult(check=..., passed=..., score=..., value=..., detail=...)`
   - Be fully deterministic — same input → same output, always
   - Never use randomness, global state, or clock-dependent logic
   - Complete within 60 seconds (network timeout budget)

5. **Write tests first.** Test file goes in `tests/checks/test_<check_name>.py`. Cover: happy path (score 100), degraded path (score 60), failure path (score 0), and N/A where applicable.

6. **Register the check.** Add it to `fynor/checks/<interface_type>/__init__.py` and `ALL_CHECKS`.

7. **Run the full suite.**
   ```bash
   pytest tests/ -v
   ruff check .
   mypy fynor/ --strict
   ```

---

## Quality Gates

Every pull request must pass all three gates (CI enforces this):

```bash
# Lint
ruff check .

# Type checking (strict mode — no ignored errors without an explanation comment)
mypy fynor/ --strict

# Tests with 90% coverage floor
pytest --cov=fynor --cov-report=term-missing --cov-fail-under=90
```

Do not suppress mypy errors with `# type: ignore` without a comment explaining why.

---

## Fixing a Bug

1. Write a failing test that reproduces the bug.
2. Fix the bug.
3. Confirm the test passes.
4. If the bug was a false positive or false negative on a check, document it in the check's `Known Failure Modes` section in `docs/adr/ADR-03-check-taxonomy.md`.

---

## Pull Request Guidelines

- **One concern per PR.** Bug fix, new check, or refactor — not all three.
- **Title format:** `fix: <what>`, `feat: <what>`, `docs: <what>`, `refactor: <what>`, `test: <what>`
- **Description:** include what the change does, why it is correct, and how to test it manually.
- **Tests:** every PR that touches `fynor/` must include or update tests.
- **No force-push to main.** Open a new PR if you need to revise a merged change.

---

## Running Checks Locally Against a Real Server

```bash
# Against a local server (SSRF protection disabled for localhost only)
fynor check --target http://localhost:8000/mcp --type mcp --skip-ssrf-check

# Against a public MCP server
fynor check --target https://mcp.example.com/mcp --type mcp

# Against a REST API
fynor check --target https://api.example.com --type rest
```

---

## Reporting a Security Vulnerability

Do **not** open a public GitHub issue for security vulnerabilities.
Email **sriram@fynor.tech** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact

You will receive a response within 48 hours.

---

## Code of Conduct

Be direct. Be respectful. Argue about ideas, not people. Disagreements about ADR amendments are expected and welcome — use evidence, not authority.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
