# CQ-028 Verification tabs

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016, CQ-012 |
| Kaneo task | CQ-028 in Kaneo (task id `syqp3227euvn3i5wmyhj6p3e`) |
| Branch | `cq-028-verification-tabs` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Borrowers, Housing, Credit & liabilities, Assets & income, Property: edit, revert to source, flag resolution, hard-pull request.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Resolving a flag resumes the pipeline.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
