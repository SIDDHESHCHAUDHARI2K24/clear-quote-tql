# CQ-028 Verification tabs

| Field | Value |
| --- | --- |
| Phase | P5 LO Tier B |
| Depends on | CQ-016, CQ-012 |
| Kaneo task | CQ-028 in Kaneo (task id `syqp3227euvn3i5wmyhj6p3e`) |
| Branch | `cq-028-verification-tabs` |
| Status | Approved 2026-09-25 (`spec-ready` in Kaneo) |

## Goal

Tabs 1–5 of the workspace show what the system imported and checked, with every problem already flagged. The LO fixes only what is flagged, and fixing it lets the automation carry on by itself.

## Scope

**Backend (owned by this item; reuse built pieces where they exist)**

- `GET /api/applications/{id}/sections/{tab}` for `borrowers`, `housing`, `credit`, `assets`, `property` → the tab's records with each field as `{field_key, value, source, overridden, original_value}` plus the tab's open flags `{id, field_key, rule, severity, message}`.
- Field edits reuse the override/revert endpoints from CQ-013/CQ-017 (`PUT` / `DELETE /api/applications/{id}/fields/{field_key}`). Row edits (add prior address, add co-borrower, edit a liability) use `POST` / `PATCH /api/applications/{id}/{collection}` for `housing_history`, `parties`, `liabilities`.
- After any edit: re-run the CQ-012 rules for that application, update flags, and if the application is NeedsAttention and no `error` flags remain, signal the CQ-011 workflow to resume from its failed stage. Activity event for every edit and flag change.
- Credit actions: `POST …/credit/import-liabilities` (mock LOS liabilities, replaces imported rows, keeps manual rows); `POST …/credit/hard-pull-request` creates a pending hard-pull consent request and emails the borrower (borrower side in CQ-033). The request lives in `consents` with `status` (`pending`, `accepted`, `declined`, `expired`) and `requested_by`/`requested_at`; add these columns in a migration if CQ-007 did not. While pending, the tab shows "Awaiting borrower consent".
- Property actions: set the subject address (county filled from zip via the mock lookup) or mark TBD; toggle `recommend_matches` (defaults on when TBD); set buy-box states and metros from the provider metro list (`GET /api/reference/metros?states=FL,NC`).
- Documents: `PATCH …/documents/{id}` marks a checklist item received; the pre-approval letter checklist reads from this.

**Frontend (tabs 1–5 in the workspace)**

| Tab | Shows | LO can |
| --- | --- | --- |
| 1 Borrowers | Borrower and co-borrower cards: name, SSN (masked, reveal for 10 s with an activity event), DOB, marital status, dependents, cell/home/work phone, emails, vesting, LLC name; "No co-applicant" state | Edit fields, add co-borrower, revert |
| 2 Housing | Current and prior addresses with own/rent and duration; total months vs 24 | Edit, add prior address |
| 3 Credit & liabilities | Representative FICO + bracket, pull type and date, liabilities table, DTI for primary | Import liabilities, request hard pull, edit a liability |
| 4 Assets & income | Verified assets, reserves required (6 months PITIA for investment), sufficiency check, employment and income for primary, document checklist | Edit, mark documents received |
| 5 Property | Address or TBD, county/state/zip, type, units; recommend-matches toggle; two-tier buy-box picker | Enter address, toggle, pick states then metros |

- Each flagged field is highlighted with its message inline and listed at the top of the tab; the tab rail badge (CQ-016) updates after each save.
- When the last blocking flag clears, a toast "All checks pass — pricing resumed" appears and the header shows the pipeline banner (CQ-016).

## Out of scope

- The borrower's consent page and the actual hard pull (CQ-033).
- Uploading documents from the LO side.

## References

- `docs/design/system-design.md` — LO Console → Application workspace table, Automation-first input model (resume from failed stage).
- `docs/design/data-field-catalog.md` — §1, §2, §3, §4.
- Built code to check in stage 1: CQ-012 rules and flags, CQ-011 workflow resume signal, CQ-013 override endpoints, CQ-016 tab routes.

## Acceptance criteria

- [ ] AC1 — Aisha Coleman: setting occupancy clears her flag, the workflow resumes, and within one pipeline run she reaches Priced with quotes (end-to-end test).
- [ ] AC2 — Ben Ford: adding a prior address that brings history to ≥ 24 months clears the housing flag; a shorter one keeps it with the months shown.
- [ ] AC3 — Editing a borrower's cell phone updates home phone when home phone was auto-copied, and leaves a manually entered home phone alone.
- [ ] AC4 — "Import liabilities" on Tom & Lisa Brandt replaces imported rows, keeps a manually added row, and updates DTI for a primary persona.
- [ ] AC5 — "Request hard pull" creates one pending consent request, sends one email to the borrower in Mailpit, and shows "Awaiting borrower consent"; a second request while pending returns 409.
- [ ] AC6 — Picking FL then Tampa and Orlando in the buy-box stores both metros; switching Kathleen's property from TBD to an address turns recommend-matches off and removes the TBD label in the header.
- [ ] AC7 — Every edit and revert writes an activity event naming the field; revealing an SSN writes an event and re-masks after 10 s.
- [ ] AC8 — Primary personas show employment, income and DTI; investment personas do not show DTI; react-doctor passes.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Integration test with Temporal test env | `test_resolve_flag_resumes_pipeline` |
| AC2, AC3 | API tests | `test_housing_history_flag`, `test_phone_copy_rule` |
| AC4 | API test | `test_import_liabilities_keeps_manual` |
| AC5 | API + Mailpit test | `test_hard_pull_request_once` |
| AC6 | API + Playwright | `test_buy_box_metros`, `e2e/property-tab.spec.ts` |
| AC7 | API test | `test_edit_audit_events` |
| AC8 | Component tests + react-doctor | `VerificationTabs.gating.test.tsx` |

## Notes for the agent

- Wave 1: section endpoints and the re-verify/resume hook; waves 2–3: the five tabs in parallel (one subagent per tab, each owning its own folder).
- Frontend item: run `react-doctor` in stages 4 and 5; build UI from `packages/ui` tokens and components.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
