---
name: Propose a new check
about: Suggest a new reliability check for a specific interface type
title: "feat(check): <check_name> for <interface_type>"
labels: enhancement, new-check
assignees: ""
---

## Failure mode this check detects

<!-- What goes wrong for AI agents when this check fails?
     Be specific: which agent behaviour breaks, and how silently? -->

## Interface type(s)

<!-- mcp | rest | graphql | grpc | websocket | soap | cli | all -->

## Proposed scoring

| Condition | Score | Pass? |
|-----------|-------|-------|
| <!-- best case --> | 100 | yes |
| <!-- degraded --> | 60 | yes |
| <!-- failure --> | 0 | no |

## Why this is not already covered

<!-- Which of the 11 existing checks does NOT catch this failure mode, and why? -->

## Evidence / citations

<!-- ADR-04 requires all thresholds to have citations.
     Link to papers, RFCs, production incident reports, or empirical data. -->

## ADR impact

- [ ] Requires ADR-03 amendment (new taxonomy entry)
- [ ] Requires ADR-04 amendment (new threshold with citation)
- [ ] No ADR change needed
