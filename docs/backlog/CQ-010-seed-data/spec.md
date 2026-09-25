# CQ-010 Seed data & demo reset

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-008, CQ-009 |
| Kaneo task | CQ-010 in Kaneo (task id `sn7qq7525r4ww2tmdpe3htp3`) |
| Branch | `cq-010-seed-data` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

10 personas from the spec, ~200 generated applications, sample documents, `make demo-reset`.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Reset completes in under 60 s; every persona number is produced by the engine.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
