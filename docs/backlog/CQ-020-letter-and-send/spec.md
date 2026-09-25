# CQ-020 Letter PDF & send workflow

| Field | Value |
| --- | --- |
| Phase | P3 LO Tier A |
| Depends on | CQ-019, CQ-015 |
| Kaneo task | CQ-020 in Kaneo (task id `n8etgbdoyhbqffavb35tibc9`) |
| Branch | `cq-020-letter-and-send` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

One click on Send produces the pre-approval PDF, locks the package, emails the borrower a clean message with the PDF and a link straight into their report, and records everything. This closes the LO half of the demo.

## Scope

**Backend (owned by this item)**

- `POST /api/packages/{id}/send` (LO auth). Refuses with 409 and the blocker list if `readiness.ready` is false. Otherwise starts a Temporal workflow `SendQuotePackage` and returns 202 with the workflow id.
- `SendQuotePackage` activities, each idempotent and retried by Temporal:
  1. **Freeze**: insert a `quote_package_versions` row (table added by CQ-022; if CQ-022 has not merged, add the same migration here) with the `ReportViewModel` snapshot (quote ids, recommendation, LO note, matches), `sent_at` and `expires_at = sent_at + 21 days`.
  2. **Render PDF**: WeasyPrint renders the CQ-019 letter template with the real portal link; stores it in MinIO at `packages/{package_id}/preapproval-letter.pdf`; saves `letter_key`.
  3. **Report link**: generate the version's opaque `report_token` and the portal URL `/report/{token}`. There is no magic link and no account is created (Decision #9, human decision 2026-09-25): the link needs a borrower session (password + email OTP, CQ-015). A signed-out borrower goes to login, or to signup with the email prefilled, then returns to the report. The report expires 21 days after send (`expires_at`).
  4. **Email**: the borrower email (HTML + plain text) with subject "Your pre-approval and numbers from Total Quality Lending", a one-screen summary (address or TBD, purchase price, recommended monthly payment and cash to close), a "See your numbers" button, and the PDF attached. Sent via SMTP (Mailpit locally) and always written to `outbox_emails`.
  5. **Record**: application status → Sent; activity event "Quote sent" with package id; CRM event via `CrmClient`.
- `GET /api/packages/{id}/letter.pdf` (LO auth) streams the stored PDF.
- Re-send: sending again creates a new sent version; the older version's report link shows "A newer version of your numbers is available" (flag on the view model).

**Frontend (LO console)**

- Wire the Send confirm dialog to `POST /send`; show progress (Rendering letter → Emailing → Done) by polling the workflow status endpoint `GET /api/packages/{id}/send-status`.
- After success: toast "Sent to {email}", status pill updates to Sent, and a "Sent versions" list appears on the Send tab with timestamp, PDF download and "Open in Outbox".

## Out of scope

- The borrower report page itself (CQ-022).
- Outbox viewer UI (CQ-029); this item only writes outbox rows.
- Production SMTP (CQ-035).

## References

- `docs/design/system-design.md` — LO Console → Send, Outbox; Architecture (WeasyPrint, Temporal, MinIO, Mailpit); Application status machine.
- `docs/design/data-field-catalog.md` — §10 letter variables, §12 CRM fields.
- Reference screen: `03-preapproval-letter-target.png`.

## Acceptance criteria

- [ ] AC1 — Sending Marcus Hale's package produces one email in Mailpit to his address, with the PDF attached and a working "See your numbers" link that opens his report (CQ-022) after the borrower signs in (or, before CQ-022 exists, points at `/report/{token}` for a version that belongs to him).
- [ ] AC2 — The PDF text contains his name, purchase price, LTV, loan term, FICO bracket, the assigned LO's NMLS, and the portal URL; it is one page on US Letter.
- [ ] AC3 — After send: status is Sent, `sent_at` and `expires_at` (+21 days) are set, one activity event and one CRM event exist, and one `outbox_emails` row references the PDF key.
- [ ] AC4 — Sending a not-ready package returns 409 with the blocker list and sends nothing.
- [ ] AC5 — Killing the worker mid-workflow and restarting it completes the send exactly once (one email, one PDF, one sent version).
- [ ] AC6 — Sending twice creates two sent versions; the first version's view model has `superseded=true`.
- [ ] AC7 — `GET /letter.pdf` returns 403 for an LO not assigned to the application.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Integration test against Mailpit API | `test_send_email_arrives_with_pdf` |
| AC2 | PDF text extraction test | `test_letter_pdf_contents` |
| AC3 | API + DB test | `test_send_records_status_events_outbox` |
| AC4 | API test | `test_send_refuses_when_not_ready` |
| AC5 | Temporal test environment with worker restart | `test_send_workflow_idempotent` |
| AC6 | API test | `test_resend_supersedes_previous` |
| AC7 | API test | `test_letter_pdf_access` |

## Notes for the agent

- WeasyPrint needs system libraries (Pango, cairo) in the backend image; add them in this item and log the Dockerfile change.
- Email HTML must be table-based and inline-styled so it renders in common mail clients; keep it to one screen.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
