# CQ-020 Letter PDF & send workflow

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-019, CQ-015 |
| Kaneo task | CQ-020 in Kaneo (task id `n8etgbdoyhbqffavb35tibc9`) |
| Branch | `cq-020-letter-and-send` |
| Status | Draft — add the `spec-ready` label in Kaneo when approved |

## Goal

One or two sentences: what the user can do when this is done, and why it matters for the demo.

## Scope

WeasyPrint pre-approval letter (TBD and address variants), MinIO storage, portal report link (borrower signs in with password + OTP per CQ-015; no magic link), email + outbox, CRM event, status Sent.

## Out of scope

- …

## References

- `docs/design/system-design.md` — sections: …
- `docs/design/data-field-catalog.md` — fields: …

## Acceptance criteria

Each criterion is testable and gets evidence in `post-dev.md`.

- [ ] AC1 — Email with PDF arrives in Mailpit; status and timeline update.
- [ ] AC2 — …

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | … | … |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
