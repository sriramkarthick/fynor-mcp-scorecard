## What this PR does

<!-- One sentence. "Fixes X", "Adds check Y for Z interface", "Refactors A to use B". -->

## Why it is correct

<!-- Explain the reasoning. Reference the ADR if a locked constraint is involved. -->

## How to test manually

```bash
# e.g.
fynor check --target http://localhost:8000/mcp --type mcp --skip-ssrf-check
```

## Checklist

- [ ] `pytest tests/ -v` passes (all existing + new tests green)
- [ ] `ruff check .` passes (no lint errors)
- [ ] `mypy fynor/ --strict` passes (no type errors)
- [ ] New or changed logic has tests
- [ ] ADR constraints respected (no weight/threshold changes without an ADR amendment)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
