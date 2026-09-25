# CQ-032 Apply wizard

| Field | Value |
| --- | --- |
| Phase | P6 Borrower Tier B/C |
| Depends on | CQ-031, CQ-011 |
| Kaneo task | CQ-032 in Kaneo (task id `qh7ollkheexd01z2stx37wwa`) |
| Branch | `cq-032-apply-wizard` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

A borrower can apply on their own in four short steps, and the application flows into exactly the same automation as an imported loan: verified, enriched and priced without the LO typing anything. This is Tier C: complete and working, with standard design.

## Scope

**Backend (owned by this item)**

- `POST /api/portal/applications` creates a draft (one open draft per borrower); `GET` returns it.
- `PATCH /api/portal/applications/{id}/draft` with `{tab, data}` autosaves one tab; server-side validation per tab returns field errors without blocking the save.
- `POST /api/portal/applications/{id}/submit` validates all tabs, then:
  1. Writes the application, parties, housing history, employment, assets, property and consent using the same models the LOS import writes (source badge "Borrower portal").
  2. Assigns an LO: the LO with the fewest active applications (ties → alphabetical); log it as an activity event.
  3. Sets status Intake and starts the CQ-011 workflow. The import stage is skipped because the data is already local; if the built workflow cannot skip it, add a `source = portal` path and log a `Decision:`.
  4. Emails the assigned LO "New application from {name}".
- SSN is encrypted at rest (reuse CQ-007's field encryption); documents upload to MinIO under `applications/{id}/documents/` (PDF, JPG, PNG; ≤ 10 MB each).

**Frontend (`apps/borrower-portal`, route `/apply`)**

| Tab | Fields | Rules |
| --- | --- | --- |
| 1 You | First/last name, email (prefilled, read-only), cell phone, DOB, SSN, marital status, dependents; current address, own/rent, years and months; prior address when under 24 months; "Add a co-borrower" (same personal fields) | Age ≥ 18; SSN 9 digits; prior address required when current < 24 months |
| 2 Property & goal | Occupancy: "I'll live there" (primary), "Long-term rental", "Short-term rental"; "Do you have a property in mind?" → address, or states and metros (two-tier picker); target price; down payment % preference (options depend on occupancy) | Price > 0; at least one metro when no address |
| 3 Income & assets | Primary: employer, years employed, monthly gross income, monthly debts. All: liquid assets. Optional uploads: pay stubs, W-2s, bank statements | Numbers ≥ 0; income required for primary |
| 4 Consent | Soft-credit-pull authorization, contact consent, terms; typed full name as signature; submit | All boxes checked; typed name matches tab 1 name (case-insensitive) |

- Stepper at the top; the next tab unlocks only when the current one validates; any completed tab can be revisited.
- Autosave 1 s after the last change, with "Saved" feedback; closing and reopening resumes at the first incomplete tab.
- After submit: confirmation screen, then home (CQ-031) shows the application in "Application received".

## Out of scope

- Real credit pulls, e-signature providers, REO and declarations sections of the full 1003.
- Editing after submit (the LO edits in CQ-028).

## References

- `docs/design/system-design.md` — Borrower Portal → Apply (Decision 6: 4 tabs), Automation-first input model.
- `docs/design/data-field-catalog.md` — §1, §2, §3, §4, §5.
- Built code to check in stage 1: CQ-011 workflow entry point, CQ-007 encryption helper, CQ-031 portal shell, buy-box reference endpoint (CQ-028 if built).

## Acceptance criteria

- [ ] AC1 — A new borrower completes all four tabs for a Tampa STR purchase; after submit the application reaches Priced with default quotes and no LO action (end-to-end with the Temporal test env or `make up`).
- [ ] AC2 — A primary applicant without income cannot pass tab 3; an applicant with 14 months at the current address must add a prior address.
- [ ] AC3 — Refreshing mid-tab 3 restores all entered values and returns to tab 3.
- [ ] AC4 — The SSN is stored encrypted (raw DB value is not the digits) and shown masked in the LO console.
- [ ] AC5 — The new application is assigned to the LO with the fewest active applications, who receives one email in Mailpit.
- [ ] AC6 — A consent row with the consent text hash, time and IP is stored at submit.
- [ ] AC7 — Uploading an 11 MB file or a .exe is rejected with a clear message; a valid PDF appears in the LO's document checklist.
- [ ] AC8 — react-doctor passes; every field has a label and error text linked by `aria-describedby`.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | End-to-end | `e2e/apply-wizard-to-priced.spec.ts` |
| AC2 | API + component tests | `test_apply_tab_validation`, `ApplyWizard.validation.test.tsx` |
| AC3 | Playwright | `e2e/apply-wizard-resume.spec.ts` |
| AC4 | DB test | `test_ssn_encrypted_at_rest` |
| AC5 | API + Mailpit test | `test_submit_assigns_lo_and_emails` |
| AC6 | API test | `test_submit_records_consent` |
| AC7 | API test | `test_document_upload_limits` |
| AC8 | react-doctor + axe | evidence in post-dev.md |

## Notes for the agent

- Wave 1: draft/submit endpoints and the workflow entry; wave 2: the four tabs in parallel (one subagent per tab); wave 3: autosave and confirmation.
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
