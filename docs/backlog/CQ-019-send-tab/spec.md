# CQ-019 Send tab & preview

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-018, CQ-021 |
| Kaneo task | CQ-019 in Kaneo (task id `cl3sboh5ibwsb0jdgapvc4um`) |
| Branch | `cq-019-send-tab` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Quote selection, recommended quote, pre-drafted note, side-by-side report and letter preview; send blocked when stale or flagged.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — The preview equals the borrower view for the same package.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
