# CQ-002 Monorepo scaffold

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-001 |
| Kaneo task | CQ-002 in Kaneo (task id `disw1i8c7oxu9qzxz0zii13j`) |
| Branch | `cq-002-monorepo-scaffold` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

pnpm workspaces (apps/lo-console, apps/borrower-portal, packages/ui, packages/api-client), uv backend project, root alembic/, Makefile, pre-commit, ruff, eslint, prettier, .env.example.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — `make lint` and `make test` pass on the empty projects.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
