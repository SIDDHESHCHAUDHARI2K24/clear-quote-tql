# CQ-029 Timeline, Outbox, Integration panel

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016, CQ-009 |
| Kaneo task | CQ-029 in Kaneo (task id `j8prs6rvebstcxromc0hu8rv`) |
| Branch | `cq-029-timeline-outbox-panel` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Activity timeline component, outbox viewer, admin integration panel with failure toggles, read-only settings page (fees, defaults, ratios).

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Forcing a pricing failure shows Needs Attention live.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
