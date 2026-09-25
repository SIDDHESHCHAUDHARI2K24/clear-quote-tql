# CQ-027 Applications list

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016 |
| Kaneo task | CQ-027 in Kaneo (task id `n44hsne4d6fminjygqwy0et2`) |
| Branch | `cq-027-applications-list` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Filters: client, LO, status, strategy, amount, state, date; flag counts per row.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Filters return the expected seed rows.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
