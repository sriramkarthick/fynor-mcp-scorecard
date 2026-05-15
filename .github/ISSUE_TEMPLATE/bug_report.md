---
name: Bug report
about: A check produces the wrong result, the CLI crashes, or scoring is incorrect
title: "fix: <short description>"
labels: bug
assignees: ""
---

## What happened

<!-- Describe what went wrong. What did you expect vs. what you got? -->

## Steps to reproduce

```bash
fynor check --target <url> --type <type>
```

<!-- Paste the full output here, including the traceback if there is one. -->

## Environment

- OS: <!-- e.g. Windows 11, macOS 14, Ubuntu 22.04 -->
- Python version: <!-- python --version -->
- Fynor version: <!-- fynor --version -->
- Target interface type: <!-- mcp | rest | graphql | grpc | websocket -->

## Which check is affected

<!-- e.g. data_freshness, schema, error_rate — or "CLI crash" if it never reaches checks -->

## Bug classification (see CONTRIBUTING.md)

- [ ] **Type A** — spec-to-code gap (the ADR is correct, the code is wrong)
- [ ] **Type B** — intent-to-spec gap (the ADR itself may need amending)
- [ ] Not sure — please help classify
