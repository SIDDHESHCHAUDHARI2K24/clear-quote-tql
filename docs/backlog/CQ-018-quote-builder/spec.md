# CQ-018 Quote builder

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-017 |
| Kaneo task | CQ-018 in Kaneo (task id `oruvrbeiljm8tu8ohnjfhxu5`) |
| Branch | `cq-018-quote-builder` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Default scenario sets (investment and primary), quote cards, Add/Edit overlay, Save & AutoQuote, manual product grid, compare, delete.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Marcus Hale gets 4 quotes; a manual pick replaces one.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
