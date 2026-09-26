# CQ-033 Hard-pull consent

| Field | Value |
| --- | --- |
| Phase | P6 Borrower Tier B/C |
| Depends on | CQ-031, CQ-028 |
| Kaneo task | CQ-033 in Kaneo (task id `sydrluy3cni59qcgqevnqy41`) |
| Branch | `cq-033-hard-pull-consent` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

A hard credit pull happens only after the borrower explicitly authorizes it, and the authorization is recorded. The LO asks from the Credit tab (CQ-028); the borrower approves or declines in the portal; the result flows back into pricing.

## Scope

**Backend (owned by this item)**

- Consent text: a versioned template (`hard_pull_v1`) stating who pulls, which bureaus, the purpose and the effect on credit score. Its SHA-256 hash is stored with each decision.
- `GET /api/portal/consents/{id}` (borrower session) → the request, the text, and the requesting LO.
- `POST /api/portal/consents/{id}/accept` with `{typed_name}` → stores the `consents` row (type `hard_pull`, text version and hash, typed name, IP, user agent, time), then runs the pull:
  1. `CreditClient.hard_pull` (mock) returns three scores; the middle one becomes `representative_fico`, `credit_pull_type = Hard_Pull`, and tradelines are refreshed into liabilities.
  2. Re-run the CQ-012 rules. If the FICO bracket changes the pricing bucket, mark quotes stale.
  3. Activity events for consent and pull; email the LO "Credit check authorized — FICO {score}".
- `POST /api/portal/consents/{id}/decline` with an optional reason → marks the request declined and emails the LO.
- The service that performs a hard pull refuses (raises, logs, 409 at the API) unless an accepted consent for that application exists. This check is in the service, not only the UI.
- Requests expire after 14 days (checked on read).

**Frontend**

- Portal: `/tasks/credit-check/[id]` page with the consent text, a checkbox "I authorize…", typed full name, "Authorize" and "Decline" buttons; confirmation states. Linked from the home task banner (CQ-031) and the request email.
- LO console, Credit tab (CQ-028): show "Awaiting borrower consent", then "Authorized {date} — hard pull complete, FICO {score}" or "Declined {date}: {reason}".

## Out of scope

- Real bureaus; soft pull changes.

## References

- `docs/design/system-design.md` — Borrower Portal → Hard-pull consent, Data model (`consents`), Emulated integrations (`CreditClient`).
- `docs/design/data-field-catalog.md` — §3 credit fields.
- Built code to check in stage 1: CQ-028 hard-pull request endpoint and pending state, CQ-009 `CreditClient`, CQ-012 rules.

## Acceptance criteria

- [ ] AC1 — Tom & Lisa Brandt: LO requests a hard pull; the borrower accepts with their typed name; a consent row with the text hash, IP and time exists; FICO updates to the middle of three mock scores; the LO gets one email.
- [ ] AC2 — Calling the hard-pull service without an accepted consent raises and writes nothing (unit test calls the service directly).
- [ ] AC3 — Declining stores the reason, emails the LO, and the Credit tab shows "Declined"; no pull happens.
- [ ] AC4 — A FICO change that crosses a pricing bucket marks that application's quotes stale; one that does not leaves them fresh.
- [ ] AC5 — A consent link opened by a different borrower returns 404; an expired request (15 days old) cannot be accepted.
- [ ] AC6 — Accepting twice does not pull twice (idempotent).
- [ ] AC7 — react-doctor passes; the consent checkbox and typed name are required and accessible.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Integration + Mailpit | `test_hard_pull_consent_flow` |
| AC2 | Unit test | `test_hard_pull_requires_consent` |
| AC3 | API test | `test_hard_pull_decline` |
| AC4 | Service test | `test_fico_bucket_change_marks_stale` |
| AC5 | API tests | `test_consent_isolation`, `test_consent_expiry` |
| AC6 | API test | `test_consent_accept_idempotent` |
| AC7 | react-doctor + component test | `CreditConsent.test.tsx` |

## Notes for the agent

- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
