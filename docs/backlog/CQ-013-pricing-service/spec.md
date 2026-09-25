# CQ-013 Pricing service & API

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-008, CQ-009 |
| Kaneo task | CQ-013 in Kaneo (task id `q2x1i5vvr84ipy6yctbu6bpk`) |
| Branch | `cq-013-pricing-service` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Enrichment with sources and overrides, Optimal Blue required-field validation, scenarios, Save & AutoQuote, manual product grid, DSCR two-pass loop, /quotes/preview.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — API tests pass; /quotes/preview responds in under 300 ms.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
