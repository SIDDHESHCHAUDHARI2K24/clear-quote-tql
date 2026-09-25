# CQ-008 Quote engine

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-004 |
| Kaneo task | CQ-008 in Kaneo (task id `tfrltrv0ypddzlexi8k2jkx9`) |
| Branch | `cq-008-quote-engine` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Pure quote_engine: P&I, PITIA, MI matrix, cash to close, qualifying rent, DSCR + bucket, cashflow, cap rate, cost segregation, config snapshot. Decimal throughout.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — All golden tests from the spec pass to the cent.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
