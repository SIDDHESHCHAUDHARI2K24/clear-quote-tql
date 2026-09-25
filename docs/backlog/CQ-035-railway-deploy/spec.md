# CQ-035 Railway deployment

| Field | Value |
| --- | --- |
| Phase | P7 Deploy & demo |
| Depends on | CQ-020, CQ-024, CQ-025, CQ-026, CQ-027, CQ-028, CQ-029, CQ-030, CQ-032, CQ-033, CQ-034 |
| Kaneo task | CQ-035 in Kaneo (task id `og7jxpwhbr5sevb2odrooiy5`) |
| Branch | `cq-035-railway-deploy` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Railway services (api, worker, 2 apps, Postgres, Valkey, Temporal template, bucket), env config, migrations and seed on deploy, SMTP relay.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Public URLs work with the seeded demo.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
