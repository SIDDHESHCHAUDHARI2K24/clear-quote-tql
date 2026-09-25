# CQ-015 Borrower auth

| Field | Value |
| --- | --- |
| Phase | P2 Auth |
| Depends on | CQ-014 |
| Kaneo task | CQ-015 in Kaneo (task id `wpmdf28umbsvrhtrtl634tab`) |
| Branch | `cq-015-borrower-auth` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Magic link (7-day expiry), email OTP, borrower sessions.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — The link in a quote email opens the right report.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
