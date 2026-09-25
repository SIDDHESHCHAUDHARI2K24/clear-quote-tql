# CQ-012 Verification rules

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-007 |
| Kaneo task | CQ-012 in Kaneo (task id `zaj9chc35lv1o16bf8hu4v18`) |
| Branch | `cq-012-verification-rules` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

1003 rules: phone copy, no-co-applicant, 24-month housing history, SSN/DOB format, assets vs cash to close + reserves, DTI (primary); flags table.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Rule tests pass; personas 7 and 8 raise their flags.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
