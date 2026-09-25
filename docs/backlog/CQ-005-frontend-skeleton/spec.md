# CQ-005 Frontend skeleton & design system

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-002 |
| Kaneo task | CQ-005 in Kaneo (task id `exsm8n0y81sz4014qlz3xrwr`) |
| Branch | `cq-005-frontend-skeleton` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Both Next.js apps; design tokens (navy, sage, type scale, mono numerals); core components (Button, MoneyInput, PercentInput, Table, Tabs, StatusPill, SourceBadge, Card, Overlay); api-client generation from OpenAPI.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — A component gallery page renders in both apps; react-doctor passes.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
