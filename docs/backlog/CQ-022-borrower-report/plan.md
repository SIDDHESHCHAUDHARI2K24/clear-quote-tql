# CQ-022 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | `quote_package_versions` already exists (P3/P4 foundation migration `bbd0e3150264`) | No new migration. `backend/app/features/quotes/send/models.py::QuotePackageVersion` is reused as-is. |
| 2 | Decision | Sent-version factory location/signature | `backend/app/features/portal/reports/versions.py::freeze_package_version(db, *, package: QuotePackage, recommendation_text=None, lo_note=None, letter_key=None, sent_at=None) -> QuotePackageVersion`. Maps `Quote`/`Scenario`/`Application`/`Property`/`Client`/`User` rows into `ReportInputs`, runs CQ-021's `build_report_view_model`, freezes the JSON as `snapshot`, sets `expires_at = sent_at + 21 days` (H2), and flips the package's prior non-superseded versions to `superseded=True`. CQ-020 calls this from its send workflow later; this item's seed extension and tests call it directly (spec.md "Notes for the agent"). |
| 3 | Decision | Response shape | `PortalReportResponse` (backend/app/features/portal/reports/schemas.py) subclasses `ReportViewModel` (CQ-021) adding `borrower_action: dict \| None` and `newest_report_token: str \| None` (only set when `superseded`). The frontend passes the response straight into `<ReportPage viewModel={...}>` (structural typing — extra fields are ignored by the component). |
| 4 | Decision | `expired`/`superseded` are recomputed at request time, not trusted from the frozen snapshot | The snapshot's `header.expired`/`header.superseded` are always `false` at freeze time (D2's "frozen at send time"). The router overrides `header.expired = now > version.expires_at` and `header.superseded = version.superseded` on every read — everything else in the snapshot is untouched. |
| 5 | Decision | Slot components live under `apps/borrower-portal/src/features/report/`, not `packages/ui/src/report/` | The coordinator's brief for this item pins `ReportMatchesSlot.tsx`/`ReportActionsSlot.tsx` to the portal app (D3), which differs from `phase-p3-p4-plan.md`'s wave table (which lists `ReportMatchesSlot.tsx` under `packages/ui/src/report/` for CQ-023's row). Following this item's explicit brief since it's the more specific, later instruction; logging the mismatch here for CQ-023's worker to reconcile if needed. `ReportPage.tsx` (packages/ui) gets two small additive optional render-prop slots (`renderMatches`, `renderActions`) so the shared component still owns page order — the portal page passes the two feature components in; CQ-019's LO preview simply omits them (nothing renders there today, same as now). |
| 6 | Decision | `SupersededBanner` needs a link to the newest version | Small additive change: `SupersededBanner` gets an optional `newestReportHref?: string` prop rendering a link when given; omitted behavior (no href) is unchanged, so existing tests/fixtures keep passing. |
| 7 | Decision | `first_name` / property label / prepay label derivation | `first_name` = `client.full_name.split()[0]`. `property_label` = `None` (renders "Property to be determined") when `Property.address_status == TBD`, else `"{street}, {city}, {state} {zip}"`. `prepay_label` = "No prepayment penalty" for PRIMARY, else `"{ppp_years}-year prepayment penalty"` from `scenario.inputs["prepayment_penalty_years"]` (raw dict key, extra to `ScenarioInputs`) or "No prepayment penalty" when absent — mirrors `pricing/scenarios/service.py`'s own default of 5 years for investment. |
| 8 | Decision | `make_borrower_session` test fixture | Added to `backend/conftest.py` (not previously present — CQ-015 added `make_staff_session` only), mirroring it: creates a real `Client` + `BorrowerAccount` + Valkey session and sets the `cq_borrower_session` cookie on the shared `client` fixture. Every CQ-022/023/024 test can reuse it. |
| 9 | Decision | Viewed-transition race safety | A single conditional `UPDATE quote_package_versions SET viewed_at = now() WHERE id = :id AND viewed_at IS NULL` under Postgres's default READ COMMITTED isolation: a concurrent second request's UPDATE blocks on the row lock, then re-evaluates the `WHERE` after the first commits and finds `viewed_at` no longer NULL, so it affects 0 rows. Only the request whose `UPDATE` affects exactly 1 row writes the activity event / status transition. |

No big gaps found against spec.md; H2 (no magic link) is already reflected in the spec text.

## Why

The borrower's report link (from CQ-020's send email, or a sent-version test factory until CQ-020 lands) opens a sign-in-gated page showing the frozen, engine-computed numbers for one sent version. This is the client-facing centerpiece (spec.md's "the page the client will judge most closely").

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend router/service/schemas | `backend/app/features/portal/reports/{__init__,router,schemas,service}.py` + `tests/` |
| Sent-version factory | `backend/app/features/portal/reports/versions.py` + `tests/test_versions.py` |
| Registry | `backend/app/core/registry.py` (register the new router) |
| Test fixture | `backend/conftest.py` (`make_borrower_session`) |
| Seed | `seed/loader.py::apply_send_fixture` (also freezes a version); `seed/tests/test_persona_statuses.py` (assert the new rows) |
| Frontend page | `apps/borrower-portal/src/app/report/[token]/page.tsx` + `page.test.tsx` |
| Frontend slots | `apps/borrower-portal/src/features/report/{ReportMatchesSlot,ReportActionsSlot}.tsx` + tests |
| Frontend auth | `apps/borrower-portal/src/features/auth/AuthFlow.tsx` (carry `next`), `LoginForm.tsx`/`SignupForm.tsx` (pass `next` through), `login/page.tsx`/`signup/page.tsx` (read `?next=`), `src/lib/nextParam.ts` (safe-redirect validator + test) |
| Middleware | `apps/borrower-portal/src/middleware.ts` (redirect to `/login?next=<path>` instead of bare `/login`) |
| packages/ui small additive | `ReportPage.tsx` (render-prop slots), `SupersededBanner.tsx` (optional link), print stylesheet (`packages/ui/src/report/print.css`), `index.ts` exports |
| api-client | regenerated after the new endpoint lands |
| e2e | `e2e/borrower-portal/report-option-switch.spec.ts`, `report-expired.spec.ts`, `report-print.spec.ts`, `report-mobile.spec.ts`, `report-login-redirect.spec.ts` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | `freeze_package_version` factory | — | `portal/reports/versions.py` | `test_versions.py` |
| T2 | `GET /api/v1/portal/reports/{token}` (fetch, viewed transition, 404 isolation, expired) | T1 | `portal/reports/{router,service,schemas}.py`, `registry.py`, `conftest.py` | `test_router.py` |
| T3 | Seed extension | T1 | `seed/loader.py` | `test_persona_statuses.py` |
| T4 | `make api-client` | T2 | `packages/api-client/**` (generated) | n/a |
| T5 | Safe `next` redirect helper + login/signup wiring + middleware | — | `lib/nextParam.ts`, `AuthFlow.tsx`, `LoginForm.tsx`, `SignupForm.tsx`, `login/page.tsx`, `signup/page.tsx`, `middleware.ts` | `nextParam.test.ts`, `middleware.test.ts`, `AuthFlow.test.tsx` |
| T6 | Report page + slots + print/mobile CSS | T4, T5 | `app/report/[token]/**`, `features/report/**`, `packages/ui` additive changes | component tests |
| T7 | E2E specs | T6 | `e2e/borrower-portal/report-*.spec.ts` | Playwright |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T5 | Backend contract and frontend auth plumbing are independent |
| 2 | T2, T3 | Both build on T1 |
| 3 | T4 | Regenerate api-client once the endpoint is stable |
| 4 | T6 | Needs the generated type + the auth plumbing |
| 5 | T7 | Needs a running stack |

(Single-agent execution in this session — tasks run sequentially in this order rather than as literal parallel subagent dispatch, since the whole item is small enough for one context.)

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/features/portal/reports/tests/test_router.py::test_get_report_returns_frozen_snapshot` (factory-based; re-checked end to end after CQ-020 merges — noted in post-dev.md) |
| AC2 | `test_router.py::test_first_view_sets_viewed_once` |
| AC3 | `e2e/borrower-portal/report-option-switch.spec.ts` |
| AC4 | `test_router.py::test_expired_flag` + `e2e/borrower-portal/report-expired.spec.ts` |
| AC5 | `test_router.py::test_report_token_isolation` |
| AC6 | `e2e/borrower-portal/report-print.spec.ts` |
| AC7 | `e2e/borrower-portal/report-mobile.spec.ts` |
| AC8 | `e2e/borrower-portal/report-print.spec.ts` (gating check) + Lighthouse/axe evidence in post-dev.md + react-doctor |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
