# CQ-034 Support form

| Field | Value |
| --- | --- |
| Phase | P6 Borrower Tier B/C |
| Depends on | CQ-031 |
| Kaneo task | CQ-034 in Kaneo (task id `udrypg58ji3ymuvwryhgxayz`) |
| Branch | `cq-034-support-form` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

A borrower who is stuck can reach a person in under a minute, and the support team gets everything they need (who, which application, what stage, which LO) without asking follow-up questions.

## Scope

**Backend (owned by this item)**

- `POST /api/portal/support` (borrower session) with `{topic, message, preferred_contact, phone?}`:
  - `topic`: `application`, `quote`, `documents`, `other`.
  - `message`: 10–2,000 characters.
  - `preferred_contact`: `email` or `phone`; phone required when `phone`.
- Creates a support request with a short reference (e.g. `SUP-7F3K2`), then emails `SUPPORT_INBOX` (setting; default `support@tql.local`) with subject "[{reference}] {topic} — {borrower name}" and a body containing: borrower name, email, phone, preferred contact, message, the borrower's latest application (id, stage, internal status, property label), the assigned LO and a link to the application in the LO console. Writes an `outbox_emails` row and an activity event on that application.
- Sends the borrower a short confirmation email with the reference.
- Rate limit: 5 requests per borrower per hour (Valkey); the 6th returns 429.

**Frontend (`apps/borrower-portal`)**

- Route `/support` in the portal shell (CQ-031 nav link): topic select, message textarea with a character counter, preferred-contact radio, phone prefilled from the profile, submit.
- Confirmation state: "Thanks — we'll be in touch by {email or phone}. Your reference is {reference}." plus the assigned LO's direct contact as an alternative.
- Logged-out users see the login page, with a "Need help signing in?" line showing the support email address.

## Out of scope

- A ticketing system, replies inside the portal, attachments.

## References

- `docs/design/system-design.md` — Borrower Portal → Support.
- Built code to check in stage 1: CQ-031 portal shell, outbox writer (CQ-020), Valkey rate-limit helper (CQ-014).

## Acceptance criteria

- [ ] AC1 — Marcus Hale submits a "quote" question; Mailpit shows one email to the support inbox with his name, email, phone, message, application stage and status, LO name and console link, and one confirmation email to him with the same reference.
- [ ] AC2 — The request writes one outbox row and one activity event on his application.
- [ ] AC3 — A 9-character message, or phone preference without a phone, is rejected with field errors.
- [ ] AC4 — The 6th request in an hour returns 429 and the page shows "Please try again later".
- [ ] AC5 — A borrower with no application can still submit; the email says "No application yet".
- [ ] AC6 — react-doctor passes; the form is fully keyboard operable with visible errors.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC2 | Integration + Mailpit | `test_support_request_emails` |
| AC3 | API test | `test_support_validation` |
| AC4 | API test | `test_support_rate_limit` |
| AC5 | API test | `test_support_without_application` |
| AC6 | react-doctor + component test | `SupportForm.test.tsx` |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
