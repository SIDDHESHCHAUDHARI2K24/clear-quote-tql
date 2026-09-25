# CQ-016 Application workspace shell

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-014, CQ-011 |
| Kaneo task | CQ-016 in Kaneo (task id `ns44zsvwb9gtn4vyyi2om3h0`) |
| Branch | `cq-016-application-workspace` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Sticky header numbers, status, tab rail with check/flag counts, note rate greyed until priced, LO sets Withdrawn/Closed.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Header matches engine output for all personas.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
