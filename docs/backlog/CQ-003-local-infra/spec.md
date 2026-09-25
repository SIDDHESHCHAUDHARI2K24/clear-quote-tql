# CQ-003 Local infrastructure

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-002 |
| Kaneo task | CQ-003 in Kaneo (task id `r9ygdvtsayxcsp57x2ax0tit`) |
| Branch | `cq-003-local-infra` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Docker Compose: Postgres, Valkey, MinIO + bucket init, Mailpit, Temporal server + UI; `make up`, `make down`, `make logs`.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — All services healthy; Temporal UI and Mailpit reachable in the browser.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
