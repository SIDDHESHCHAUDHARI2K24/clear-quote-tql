# CQ-031 Borrower home & status

| Field | Value |
| --- | --- |
| Phase | P6 Borrower Tier B/C |
| Depends on | CQ-015 |
| Kaneo task | CQ-031 in Kaneo (task id `og87fx1m2qancd3vhtykefny`) |
| Branch | `cq-031-borrower-home` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Progress bar, next action, start application.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Each persona sees its correct stage.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
