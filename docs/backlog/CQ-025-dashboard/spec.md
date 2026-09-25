# CQ-025 Dashboard

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016 |
| Kaneo task | CQ-025 in Kaneo (task id `xkbost5i2wf96mdm8k1r0k6k`) |
| Branch | `cq-025-dashboard` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Status tiles, attention queue, stale quotes list, activity feed.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Tile counts match seed queries.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
