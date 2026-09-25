# CQ-031 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Route path | Spec says `GET /api/portal/me`; per AGENTS.md/worker guide every route lives under `/api/v1`, and the coordinator prompt pins the exact path `GET /api/v1/portal/me`. New sub-feature `features/portal/home/` with `router = APIRouter(prefix="/portal", tags=["portal-home"])`, route `/me`. |
| 2 | Decision | Stage/label mapping function | One function `service.stage_and_label(status, *, has_ever_sent, lo_first_name) -> tuple[PortalStage, str]` is the single source of truth (spec.md "Notes for the agent"). `has_ever_sent` = existence of any `quote_package_versions` row for the application (any version, not just non-superseded) — this is what distinguishes STALE-never-sent (`in_review`) from STALE-after-a-send (`preapproved`), per the coordinator prompt. |
| 3 | Decision | `next_action` precedence | Not fully pinned by spec.md's table (it lists four values with no explicit priority). Decided, per the coordinator's persona examples (Marcus → `view_report`; Luis/OptionSelected → `none` + secondary token): (a) `stage == option_selected` → always `none`, with `secondary_report_token` set to the latest non-superseded version's token if one exists (Luis: AC3). (b) `stage == closed` → always `none`. (c) else if a `consents` row exists for the application with `status = pending` and (`expires_at IS NULL` or `expires_at > now()`) → `authorize_credit_check` (that row's id) — this outranks `view_report` because a pending ask is the more urgent "one thing to do". (d) else if a non-superseded `quote_package_versions` row exists for the application → `view_report` (its `report_token`). (e) else `none`. Draft entries (CQ-032a's `application_drafts`) always get `continue_application` and never fall through this ladder — they are a separate synthetic item, not a mapped `Application` row. |
| 4 | Decision | Draft representation | `application_drafts` is a different table from `applications` (no shared PK). A borrower's *open* draft (`submitted_application_id IS NULL`) is rendered as one extra `PortalApplicationOut` with `id = draft.id`, `stage = draft`, `label = "Continue your application"`, `next_action = {type: continue_application, draft_id: draft.id}`, `lo = null` (no LO is assigned pre-submit). It is prepended to the list (an in-progress application is the most actionable item). |
| 5 | Decision | Greeting fields | `first_name` = `client.full_name.split()[0]` (same convention as `portal/reports/versions.py:196`); `email` = `borrower.email` (the signed-in `BorrowerAccount`'s own login email — no extra query, and it's set from the same value as `client.email` at signup). |
| 6 | Decision | LO contact | `Application.lo_id` → `User` row → `{name: full_name, phone, email}`. Not the client's `assigned_lo_id` (the two are set equal at seed/signup time, but `lo_id` is what a workspace reassignment would actually change). |
| 7 | Decision | No-application empty state copy | Spec.md says "Start your application" (links to CQ-032's wizard; shows 'Coming soon' until CQ-032 exists)" but the worker guide/coordinator overrides this: `/apply` is already a stub route (P5/P6 foundation) that always renders (CQ-032b fills it later), so the link always works — no "Coming soon" state is built. Logged per the coordinator's instruction. |
| 8 | Decision | AC2 word-scan test | A dedicated `test_portal_hides_internal_states` seeds one application per `ApplicationStatus` value (not just Aisha's `needs_attention`) via the local `make_application` factory, calls `GET /portal/me` for each, and asserts none of "attention", "flag", "error" (case-insensitive) appear anywhere in the raw JSON text — stronger than scanning only Aisha's persona. |
| 9 | Decision | Frontend progress bar mapping | `stage` values `applied/in_review/preapproved/option_selected` map to steps 1–4 of the 4-step bar (`STAGE_STEPS` in `src/features/home/`). `closed` and `draft` are rendered as their own card layouts (label + next action, no 4-step bar) — this is presentation shape, not re-deriving borrower-facing text from internal status, so it doesn't violate "frontend renders only stage and label, with no status logic". |

No big gaps.

## Why

A borrower who signs in today sees a bare placeholder. This item gives them a plain-language status per application and exactly one next action, with all internal LO-facing vocabulary ("Needs Attention", "flag", "error") kept out of the response — the mapping lives in one backend function so the frontend never re-derives it.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend feature | create `backend/app/features/portal/home/{__init__,router,schemas,service}.py` + `tests/` |
| Registry | modify `backend/app/core/registry.py` (one line) |
| Frontend page | modify `apps/borrower-portal/src/app/(portal)/page.tsx`; rewrite `page.test.tsx`; move the unrelated stub-page tests (Support/Apply/Credit-check) it currently holds into a new `stub-pages.test.tsx` (small logged necessity — those stub pages belong to CQ-032/033/034, not this item, and must keep working) |
| Frontend feature | create `apps/borrower-portal/src/features/home/{ProgressBar,ApplicationCard,ConsentBanner,api,index}.tsx/.ts` + tests |
| e2e | create `e2e/borrower-portal/portal-home.spec.ts` |
| Generated | `packages/api-client` via `make api-client` |
| Docs | `docs/backlog/CQ-031-borrower-home/{plan,post-dev,handoff}.md`, evidence screenshots |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Schemas + stage/label mapping function | — | `portal/home/schemas.py`, `portal/home/service.py` | `tests/test_service.py` (every `ApplicationStatus` × has_ever_sent combination in the spec table; AC1 personas' expected stage/label) |
| T2 | `next_action` resolution + draft + LO contact | T1 | `portal/home/service.py` | `tests/test_service.py` (view_report token, authorize_credit_check precedence, option_selected → none + secondary token, draft entry, closed → none) |
| T3 | Router + registry line | T1, T2 | `portal/home/router.py`, `core/registry.py` | `tests/test_router.py` (AC1 parametrized over 10 personas, AC2 word-scan, AC3 Marcus/Luis, AC4 empty state — noapp borrower, AC5 isolation) |
| T4 | api-client regen | T3 | `packages/api-client` | `make api-client` diff review |
| T5 | Frontend home feature (progress bar, application card, consent banner, api.ts) | T4 | `src/features/home/**` | Vitest per component |
| T6 | Frontend page wiring | T5 | `(portal)/page.tsx`, `page.test.tsx`, `stub-pages.test.tsx` | `page.test.tsx` (greeting, cards, empty state, banner) |
| T7 | e2e + evidence | T6 | `e2e/borrower-portal/portal-home.spec.ts` | Playwright at 1280/375px; Lighthouse; react-doctor |

## Wave schedule (stage 3)

Single worker, no sub-agents (unit is small enough) — sequential waves for file ownership clarity only.

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | Pure mapping logic first (TDD unit tests, no DB) |
| 2 | T3, T4 | Router + contract regen before any frontend code reads it |
| 3 | T5, T6 | Frontend feature then page wiring |
| 4 | T7 | e2e last, against a running stack |

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/features/portal/home/tests/test_router.py::test_portal_stage_mapping` (parametrized, 10 personas via seed factory) |
| AC2 | `test_router.py::test_portal_hides_internal_states` (Aisha + full status sweep, raw-text scan) |
| AC3 | `test_router.py::test_next_action_view_report_and_option_selected` (Marcus, Luis); `e2e/borrower-portal/portal-home.spec.ts` |
| AC4 | `apps/borrower-portal/src/features/home/ApplicationsList.test.tsx` (or `page.test.tsx`) empty-state case; backend `test_router.py::test_empty_state_no_applications` (noapp borrower) |
| AC5 | `test_router.py::test_portal_me_isolation` |
| AC6 | Playwright viewport (375px, no h-scroll) + Lighthouse + `npx react-doctor -y --blocking error`; evidence in `post-dev.md` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
