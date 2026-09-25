# CQ-011 Temporal pipeline

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-009, CQ-012, CQ-013 |
| Kaneo task | CQ-011 in Kaneo (task id `pkzooifqak5acpcetl7y3xwy`) |
| Branch | `cq-011-temporal-pipeline` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

One workflow per application; activities import, verify, enrich, validate, auto-price, draft quote set; resume from the failed stage; activity events.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Each persona ends in its expected status.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
