# CQ-022 Borrower report page

| Field | Value |
| --- | --- |
| Phase | P4 Borrower Tier A |
| Depends on | CQ-021, CQ-015 |
| Kaneo task | CQ-022 in Kaneo (task id `lu2ozfdjwkillbh9z0tymw42`) |
| Branch | `cq-022-borrower-report` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Report header, option switcher driving hero numbers, collapsible sections, print stylesheet, expired state.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Print to PDF is clean; the expired persona shows the banner.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
