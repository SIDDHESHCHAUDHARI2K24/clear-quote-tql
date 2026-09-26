# CQ-019 — Implementation plan

Written by the agent in stages 1–3. Every acceptance criterion maps to a test (see the map below).

## Decisions & questions (stage 1)

Gap check against `spec.md`, `system-design.md` (Send tab 7, Quote report, Decisions 3–5, 9), catalog §3/§10/§12 and `phase-p3-p4-plan.md` (H1–H5, D1–D7). No big gaps.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Routes live under `/api/v1` (the spec writes `/api/...`) | Decided: every feature router is mounted at `/api/v1` by `core/registry.py`. |
| 2 | Decision | One draft package per application | Decided: `quote_packages` stays the working package (D2). `GET /applications/{id}/package` returns the application's newest package, creating the default draft under `lock_application` when none exists. A sent package (Grace Kim, Luis Romero) is still the working package; CQ-020 freezes new versions from it. |
| 3 | Decision | AC2 parity | Decided: one function, `app.features.quotes.send.view_model.build_package_view_model(db, package, *, recommendation_text, lo_note, as_of, expires_at, expired=False, superseded=False)`, holds the Quote→`ReportInputs` mapping, the CQ-021 builder call and CQ-023's `compute_matches_for_package`. `freeze_package_version` calls it with the send time; `GET /packages/{id}/report` calls it with the live draft and today. The contract test allows only `header.prepared_at`, `header.expires_at`, `header.expired` and `header.superseded` to differ (plus the portal-only `borrower_action`/`newest_report_token` wrapper fields). |
| 4 | Decision | Recommendation text storage | Decided: new nullable column `quote_packages.recommendation_text` (one migration off `e419a34bcdbd`). Re-drafted by the server whenever the recommended quote changes; the frontend only displays it. `freeze_package_version` uses `package.recommendation_text` when the caller passes none, so the sent report says exactly what the preview said. |
| 5 | Decision | Recommendation wording | Decided: `"{dp}% down · {Par/Buydown/Manual} pricing at {rate}%{, prepay}." + one sentence by label`. Investment adds `, no prepay` or `, N-year prepay`; primary never mentions a PPP (AGENTS.md rule). Par: "It balances your monthly payment and cash needed at closing." Buydown: "It lowers your rate and monthly payment for points paid at closing." Manual: "It is the product your loan officer picked for your goals." |
| 6 | Decision | Default draft | Decided: `default_package_selection(db, application)` reuses CQ-018's `list_application_scenarios` ordering: recommended quote (`applications.recommended_quote_id`), else the first group's Par (else its first card); then the remaining cards in group order, Par/Buydown/Manual, up to 3 in total. The seed's `apply_send_fixture` calls the same function (CQ-018 review n1). |
| 7 | Decision | At most 3 quotes in a package | Decided: `PUT` rejects more than 3 (catalog §10 "Compares up to 3 options"). |
| 8 | Decision | Send radio vs Builder star | Decided: `PUT` with a new `recommended_quote_id` also sets `applications.recommended_quote_id` (one recommendation per application, CQ-018) and logs `quote.recommended`; otherwise the builder star and the report would disagree. |
| 9 | Decision | Stale rule for readiness | Decided: a selected quote is stale when `quote.stale` OR `priced_at` is older than 21 days (catalog §12 `is_rate_stale`). The seed priced Grace Kim's quotes "now" although her package was sent 25 days ago, so `apply_send_fixture` now backdates the package quotes' `priced_at` to the send time (timestamps only). Grace Kim is then blocked with "Quotes are out of date" → Pricing. |
| 10 | Decision | Spec's flag severity "error" | Decided: maps to `FlagSeverity.BLOCKING` (there is no `error`). The blocker message names the field and rule, e.g. "Open flag: Occupancy type — required for pricing". |
| 11 | Decision | Manual quote whose product left the grid (CQ-018 follow-up) | Decided: a selected Manual quote that is stale while its scenario's Par was priced later is "no longer offered": readiness adds `quote_not_offered` "1 manual quote is no longer offered — delete or re-pick" → Pricing (on top of the stale blocker). |
| 12 | Decision | Blocker order | Decided: stale quotes, not-offered quotes, open blocking flags, no quotes, no recommended quote, missing borrower email. The Send button tooltip shows the first. |
| 13 | Decision | Letter data | Decided: par quote = the package's first `Par` quote (recommended first), else the recommended quote. FICO bracket in 20-point bands (`780+`, `760–779`, … `Below 620`). Assets line = `Verified Assets $NK+` from `quote_engine.verified_assets_floor` (sum of `assets.verified_amount`, floored to $1,000). Checklist rows come from `documents`: received → "received", else "requested". Vesting in an LLC → the LLC name as buyer. |
| 14 | Decision | Portal URL placeholder | Decided: `render_package_letter(db, package, *, portal_url=None)`. `None` (the Send-tab preview) renders the line "See every option we priced in your Clear Quote report — the link arrives in your quote email." CQ-020 passes the real `/report/{token}` URL and the template renders it as a link. No new setting. |
| 15 | Decision | Prepay label in the report | Decided: the shared builder labels an investment scenario with no PPP set as the 5-year default it was priced at (CQ-018's rule, `ob_request._DEFAULT_INVESTMENT_PPP_YEARS`); the old freeze said "No prepayment penalty" for it. |
| 16 | Decision | CQ-018 review minors | n2: `POST /applications/{id}/scenarios` takes `lock_application`. n3: `recommend_quote`/`delete_quote` re-read the quote after the lock and 404 when gone. The lock test now also covers scenario create and manual pick. |
| 18 | Decision | Code review fixes | Recommendation text is re-drafted from the recommended quote's current values on read/preview/freeze; only a *sent* package blocks a quote delete (a delete drops the quote from unsent drafts); the Builder star updates the unsent draft and the default draft sets the application's recommendation when it has none. |
| 17 | Decision | Letter preview isolation | Decided: `letter.html` is served with `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:` and the UI renders it in `<iframe sandbox="">` via `srcDoc` fetched with the session cookie. |

## Why

The LO needs one screen to choose what the borrower gets, confirm the recommendation and see exactly the report and letter before sending (spec Goal).

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Migration | `alembic/versions/*_quote_packages_recommendation_text.py` |
| Package + readiness API | `backend/app/features/quotes/send/{models,schemas,service,default_draft,readiness,view_model,router}.py`, `tests/` |
| Letter | `backend/app/features/quotes/pdf/{__init__,service}.py`, `templates/preapproval_letter.html`, `tests/` |
| Engine helper | `backend/app/features/pricing/engine/quote_engine.py` (`verified_assets_floor`) |
| Shared builder refactor | `backend/app/features/portal/reports/versions.py` |
| Seed | `seed/loader.py::apply_send_fixture` (+ its call site) |
| CQ-018 minors | `quotes/builder/service.py`, `pricing/scenarios/router.py`, `quotes/builder/tests/test_review_round1.py` |
| Registry / client | `core/registry.py`, `packages/api-client` (generated) |
| Frontend | `apps/lo-console/src/app/applications/[id]/send/page.tsx`, `apps/lo-console/src/features/send/**` |
| E2E | `e2e/lo-console/send-tab-draft.spec.ts` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Migration + model column | — | alembic, `send/models.py` | `alembic heads` = 1 |
| T2 | Shared view-model builder; freeze refactor | T1 | `send/view_model.py`, `portal/reports/versions.py` | `test_report_view_model_same_for_lo_and_portal`, existing CQ-022 tests |
| T3 | Default draft, recommendation text, package GET/PUT, report route | T2 | `send/default_draft.py`, `service.py`, `schemas.py`, `router.py`, registry | `test_default_package_draft`, `test_put_package_*` |
| T4 | Readiness | T3 | `send/readiness.py` | `test_readiness_blockers[grace_kim, aisha_coleman]` |
| T5 | Seed uses default draft | T3 | `seed/loader.py` | seed persona status tests |
| T6 | api-client regen | T3, T4 | `packages/api-client` | `make lint` (tsc) |
| T7 | Letter template + render + route | T3 | `quotes/pdf/**`, `send/router.py` | `test_letter_tbd_variant`, `test_letter_llc_and_address_variants` |
| T8 | Send tab UI | T6, T7 | `app/applications/[id]/send/**`, `features/send/**` | Vitest (`SendTab.test.tsx`, no-money-math), react-doctor |
| T9 | E2E | T8 | `e2e/lo-console/send-tab-draft.spec.ts` | Playwright |
| T10 | CQ-018 minors n2/n3 | — | builder service, scenarios router | `test_every_builder_write_locks_the_application_row`, `test_write_404s_when_quote_deleted_before_lock` |

## Wave schedule (stage 3)

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T10, T1, T2, T3, T4, T5, T6 | Contract first: package, readiness, report endpoints and the regenerated api-client |
| 2 | T7 | Letter template needs the package service |
| 3 | T8, T9 | UI consumes the generated client and the letter route |

Single agent, so waves run in order; no two tasks in a wave touch the same file except `send/router.py` (T3 then T7, sequential).

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/features/quotes/send/tests/test_package.py::test_default_package_draft` |
| AC2 | `backend/app/features/quotes/send/tests/test_report.py::test_report_view_model_same_for_lo_and_portal` |
| AC3 | `backend/app/features/quotes/pdf/tests/test_letter.py::test_letter_tbd_variant` |
| AC4 | `backend/app/features/quotes/pdf/tests/test_letter.py::test_letter_llc_and_address_variants` |
| AC5 | `backend/app/features/quotes/send/tests/test_readiness.py::test_readiness_blockers[grace_kim, aisha_coleman]` + `SendTab.test.tsx` (button disabled) |
| AC6 | `e2e/lo-console/send-tab-draft.spec.ts` |
| AC7 | react-doctor + `SendTab.test.tsx` iframe sandbox assertion + Playwright DOM assertion |

## Progress

- [x] T10
- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
- [x] T8
- [x] T9
