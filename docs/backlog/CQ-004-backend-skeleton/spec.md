# CQ-004 Backend skeleton

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-003 |
| Kaneo task | CQ-004 in Kaneo (task id `h69p3fiuis7d6xx94vh6sklh`) |
| Branch | `cq-004-backend-skeleton` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

FastAPI app factory, pydantic-settings, async SQLAlchemy session, error model, feature router registry, /health, pytest with test DB, OpenAPI export script.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — /health reports DB, Valkey, MinIO and Temporal status; test suite runs against a test DB.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
