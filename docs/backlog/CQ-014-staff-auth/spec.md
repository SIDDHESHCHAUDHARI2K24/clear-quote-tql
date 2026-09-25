# CQ-014 Staff auth

| Field | Value |
| --- | --- |
| Phase | P2 Auth |
| Depends on | CQ-004, CQ-007 |
| Kaneo task | CQ-014 in Kaneo (task id `pf867pgf6t8kvnq4v8ngn051`) |
| Branch | `cq-014-staff-auth` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

Password + email OTP, sessions, roles (LO, Manager, Admin), Valkey rate limits, LO sees only own files.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Auth tests pass; OTP email arrives in Mailpit.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
