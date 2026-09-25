# CQ-030 Stale quote job

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-011 |
| Kaneo task | CQ-030 in Kaneo (task id `vx3bu30y7asxddivv7ao4kv2`) |
| Branch | `cq-030-stale-quote-job` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Temporal schedule marks quotes older than 21 days stale; re-price action.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Grace Kim's quote flips to Stale.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
