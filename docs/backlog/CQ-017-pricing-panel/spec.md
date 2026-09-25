# CQ-017 Pricing panel

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-016, CQ-013 |
| Kaneo task | CQ-017 in Kaneo (task id `lky9qv864ao119rajk7ujqd8`) |
| Branch | `cq-017-pricing-panel` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Pricing inputs, linked % and $, source badges, override and revert, live breakdown, stale marker.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Editing price updates the breakdown instantly; revert restores the source value.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
