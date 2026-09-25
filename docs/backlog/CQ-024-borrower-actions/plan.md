# CQ-024 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Source of truth for `borrower_action` | `QuotePackageVersion.borrower_action` (JSONB: `{type, quote_id, message, at}`) is the source of truth — it's what `portal/reports/service.py` already returns to the report page. `QuotePackage.borrower_action` (the coarse `BorrowerAction` enum: `option_selected`/`inquiry`) is mirrored from it on every action (move_forward → `option_selected`; ask_other/ask_updated → `inquiry`) so a future LO-console reader that only wants the coarse status doesn't have to join the version table. Nothing reads `QuotePackage.borrower_action` yet (grepped: only `seed/loader.py` writes it today) — mirroring is cheap insurance, not a hard requirement. |
| 2 | Decision | Row locking | `SELECT ... FOR UPDATE` on `QuotePackageVersion`, then `QuotePackage`, then `Application` (in that order — token → package → application, same order `service.py::get_report_for_token` already walks) inside `submit_action`, so a double-click / two tabs can't both pass the status check and both send an email. Mirrors CQ-022's `freeze_package_version` `FOR UPDATE` pattern and CQ-016's `patch_application_status` fix. |
| 3 | Decision | Superseded blocks every action type, not just move_forward/ask_other | Spec's rules table only states expiry/status conditions for move_forward/ask_other and "Version expired only" for ask_updated, but the carried CQ-022 review finding #2 says "Actions must be unavailable on a superseded version ... The API returns 409" without scoping it to a type. Checked first, before the per-type rules: any action on a superseded version 409s (frontend already hides the whole slot in that case, so this is a defense-in-depth server check, not a reachable UI path). |
| 4 | Decision | `quote_id` validation | Validated against the **frozen snapshot's** `options[].quote_id` (never a live `Quote` row — the version is immutable once sent), per the task's "quote_id must be one of the version's snapshot options (else 422)". Required for `move_forward`. Optional for `ask_other` (the dialog always has a "currently selected option" in context, so the frontend always sends it, but the backend doesn't hard-require it — a borrower could theoretically ask a general question). Ignored for `ask_updated` (expired report, no option is "current"). |
| 5 | Decision | Assigned LO source | `Application.lo_id` (already loaded to check ownership/lock; avoids a second row fetch for `Client.assigned_lo_id`, which is expected to always match it — no code path reassigns one without the other today). |
| 6 | Decision | CRM `contact_id` | `Client.crm_contact_id or str(Client.id)` — first real caller of `crm_contact_id` in the codebase (grepped: field exists, unused). Falls back to the client's own id, consistent with the mock CRM having no real external ids. |
| 7 | Decision | Email templates | Plain Python string-building functions (`portal/actions/templates.py`), not Jinja files — matches the existing convention (`auth/borrower/service.py`'s `_OTP_EMAIL_HTML`/`_EXISTING_ACCOUNT_HTML`), just table-based/inline-styled per this item's brief (a small `_shell()` helper wraps a definition-list-style `<table>`). No Jinja dependency is exercised (H4's `jinja2`/`weasyprint` are reserved for CQ-020's PDF letter). |
| 8 | Decision | Frontend refetch mechanism | `ReportView.tsx` extracts its GET into a `loadReport()` callback (kept as the effect body, called again on demand) and passes it down through the existing `renderActions` render-prop closure as `onActionTaken`, along with `token` and `borrowerAction={report.borrower_action}` — **no new prop is added to `ReportView`'s or `ReportPage`'s public interface**; only the JSX inside `ReportView`'s existing `renderActions` callback changes, and `ReportPage.tsx` (packages/ui, not owned by this item per plan.md D3) is untouched. On a successful action or a 409, the slot calls `onActionTaken()`, which re-GETs `/portal/reports/{token}` and updates `ReportView`'s state — the same source of truth the rest of the page already renders from, so the header/superseded/expired/borrower_action state can never drift from what the slot displays. |
| 9 | Decision | `ask_updated`/`ask_other` don't show a terminal "confirmed" state | Spec's "Confirmed state replaces the buttons" describes `move_forward` only (it's the one action that permanently blocks further move_forward/ask_other — `status → OptionSelected`, and OptionSelected onward always 409s both). `ask_other`/`ask_updated` set `Inquiry` but remain re-askable (the rules table keeps `Sent, Viewed, or Inquiry` valid for `ask_other`, and `ask_updated` only cares about expiry) — after either succeeds, the slot shows a small transient "Sent — {LO first name} will be in touch." note and leaves the relevant button(s) active, instead of replacing them. |
| 10 | Decision | Freeze script for E2E | CQ-023's `backend/scripts/freeze_version.py` is not on this branch's base (`git log` shows only CQ-021/016/022 merged into `phase-p3-p4`). Wrote `backend/scripts/freeze_sent_version.py --persona <key>` (own file, distinct name) per the brief's explicit fallback instruction. |
| 11 | Question (big gap) | none | No big gap hit — CQ-022's report endpoint, `freeze_package_version`, and CQ-016's summary polling all exist and match what this item needs. |
| 12 | Decision | PR #8 review round 1, MINOR: spec.md:27's "ask_other is the only type allowed after an Inquiry is answered by a new version" | Deferred to CQ-020: needs a version↔inquiry link, created by the send workflow; CQ-020 must enforce it. Nothing in this item's schema links a `QuotePackageVersion` back to the specific `ask_other`/`ask_updated` inquiry it answers — the only thing that mints a new version today is `freeze_package_version` (CQ-022/023's existing helper), and only CQ-020's future send/resend workflow decides when a resend happens in response to an inquiry. Building that link now, with no caller that resends, would be speculative and untestable within this item's own scope. |

## Why

Closes the demo loop from the borrower's side: after CQ-022 lets a borrower view their frozen report, this item lets them say "move forward" or "ask about another option" (or, once expired, "ask for updated numbers"), and the LO finds out immediately (email, activity timeline, CRM event) without the app ever implying a locked rate or a binding acceptance.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend: action endpoint | `backend/app/features/portal/actions/{__init__,schemas,service,router,templates}.py` + `tests/` (new feature package) |
| Backend: report 404 message fix | `backend/app/features/portal/reports/service.py` (modify) |
| Backend: router registration | `backend/app/core/registry.py` (modify) |
| Backend: dev freeze script | `backend/scripts/freeze_sent_version.py` (new) |
| Frontend: actions slot | `apps/borrower-portal/src/features/report/ReportActionsSlot.tsx` + `.test.tsx` (rewrite) |
| Frontend: dialogs/hooks | `apps/borrower-portal/src/features/actions/*` (new: `api.ts`, `MoveForwardDialog.tsx`, `AskOtherDialog.tsx`, tests) |
| Frontend: minimal wiring | `apps/borrower-portal/src/features/report/ReportView.tsx` (modify — `renderActions` closure only, per Decision 8) |
| Generated client | `packages/api-client/**` (regenerated via `make api-client`, never hand-edited) |
| E2E | `e2e/borrower-portal/report-expired-actions.spec.ts`, `e2e/borrower-portal/move-forward.spec.ts`, `e2e/borrower-action-reflects-in-console.spec.ts` |
| Docs | `docs/backlog/CQ-024-borrower-actions/{plan,post-dev,handoff}.md`, `evidence/` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | `portal/reports/service.py` 404 message fix | — | `portal/reports/service.py` | `test_report_not_found_message_matches_for_missing_and_foreign_token` |
| T2 | Action schemas + templates | — | `portal/actions/schemas.py`, `templates.py` | `test_templates.py::test_no_binding_language` |
| T3 | Action service (rules, locking, email, CRM, activity) | T2 | `portal/actions/service.py` | `test_service.py` (one test per rule row + race test) |
| T4 | Action router + registry | T3 | `portal/actions/router.py`, `core/registry.py` | `test_router.py` (AC1–AC4 API-level) |
| T5 | `make api-client` regenerate | T4 | `packages/api-client/**` | n/a (generated) |
| T6 | Dev freeze script | T4 | `backend/scripts/freeze_sent_version.py` | manual E2E use |
| T7 | `ReportActionsSlot.tsx` + dialogs | T5 | frontend files above | Vitest suite (states, dialogs, focus trap, 409/network handling) |
| T8 | `ReportView.tsx` wiring | T7 | `ReportView.tsx` | existing `ReportView.test.tsx` extended |
| T9 | E2E specs | T6, T8 | `e2e/**` | Playwright, see AC map |
| T10 | Docs/evidence | T9 | `post-dev.md`, `evidence/` | — |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | No dependencies; the schema/template contract other tasks build on |
| 2 | T3 | Needs schemas |
| 3 | T4, T6 | Needs service; freeze script only needs the versions factory (already merged) |
| 4 | T5 | Needs the router to exist for the OpenAPI schema |
| 5 | T7 | Needs the generated client types |
| 6 | T8 | Needs the slot's final prop shape |
| 7 | T9 | Needs a running stack |
| 8 | T10 | Last |

Single-agent execution (no parallel subagents dispatched for this item — the task set is small enough, and contract-first ordering above is followed sequentially instead).

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/features/portal/actions/tests/test_router.py::test_move_forward_sets_option_selected_and_sends_one_email` (+ CRM/activity assertions in the same test); E2E slot check (move-forward.spec.ts) against Marcus Hale via Mailpit |
| AC2 | `test_router.py::test_move_forward_twice_second_is_409_no_new_email`; frontend `ReportActionsSlot.test.tsx::confirmed state renders after move_forward, and a 409 on a second click refetches instead of erroring` |
| AC3 | `test_router.py::test_ask_other_requires_message`, `test_ask_other_sets_inquiry_and_emails_message` |
| AC4 | `test_router.py::test_expired_allows_only_ask_updated`; `e2e/borrower-portal/report-expired-actions.spec.ts` (Grace Kim) |
| AC5 | `backend/app/features/portal/actions/tests/test_templates.py::test_no_binding_language`; `apps/borrower-portal/src/features/report/ReportActionsSlot.test.tsx::no binding language in rendered copy` |
| AC6 | `e2e/borrower-action-reflects-in-console.spec.ts` |
| AC7 | react-doctor run in stages 4/5 (post-dev.md); `apps/borrower-portal/src/features/actions/MoveForwardDialog.test.tsx::traps focus and closes on Escape` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
- [x] T8
- [x] T9
- [x] T10
