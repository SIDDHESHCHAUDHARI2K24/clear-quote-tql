# CQ-009 Mock integrations

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-007 |
| Kaneo task | CQ-009 in Kaneo (task id `kj6ktr2wmayhugqzjv70882k`) |
| Branch | `cq-009-mock-integrations` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

9 adapter protocols (LOS, Pricing, Rent, STR, Tax, Insurance, Credit, PropertySearch, CRM) with mock implementations, provider tables, simulated latency, failure toggles.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Contract tests per adapter; a forced failure returns a named error.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
