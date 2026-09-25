# CQ-016 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | D6 access (plan.md) | Keep Decision #11: `get_scoped_application` 404s an out-of-scope application. AC5 is read as "404, not 403"; test name kept as `test_summary_access_by_role`. UI shows a "not found or no access" page for a 404 on the summary route. |
| 2 | Decision | D7 stage writes | New `PipelineStage` enum in `app/workflows/constants.py` with 6 running-stage names (`importing`, `verifying`, `enriching`, `validating`, `pricing`, `drafting_quotes`). Each pipeline activity sets `applications.last_pipeline_stage` to its own name at the start of its work. On a terminal outcome the stage is overwritten with the *application status string* it lands on: `"needs_attention"` (stopped) or `"priced"` (done) — reusing `ApplicationStatus` values instead of inventing a second vocabulary. `last_pipeline_stage is None or in {"needs_attention", "priced"}` = terminal; the frontend polls on that same rule (`apps/lo-console/src/features/workspace/pipeline.ts`). |
| 3 | Decision | "Purchasing power" header number | No purchasing-power engine exists anywhere in the codebase (`pricing/scenarios/service.py::_purchase_price`, "Decision 7"). Header "purchasing power" = the `purchase_price` stored on the application's *current scenario*'s `ScenarioInputs` (== `application.requested_price` at scenario-creation time). Same convention as the existing pricing service. |
| 4 | Decision | "Current scenario" for header numbers | The scenario behind `application.recommended_quote_id`'s quote when set, else the application's most-recently-created `Scenario` row, else `null` (no scenario yet — e.g. Aisha Coleman, stuck before pricing). Down payment %, $, and PPP years all come from this scenario. Down payment $ is computed as `purchase_price * down_payment_pct` (`ROUND_HALF_UP` to cents), matching `quote_engine`'s own rounding convention, **without adding a field to `QuoteComputation`** — per the coordinator's message (2026-09-25): CQ-021 (PR #4, still open) is adding `down_payment_amount` to the engine itself, and this item's owned files exclude `backend/app/features/pricing/engine/`. Deriving it directly from `ScenarioInputs` needs no engine change and needs no merge coordination once #4 lands (the two computations are the same formula/rounding). |
| 5 | Decision | Note rate | `null` unless `application.recommended_quote_id` is set, in which case it is that `Quote.rate` verbatim (not re-derived through the engine) — matches AC3. |
| 6 | Decision | Tab state rule | A tab is `flagged` (with its open-flag count) whenever it has ≥ 1 unresolved `flags` row. Otherwise: `pending` while `application.status == INTAKE` (the automated chain has not started evaluating anything yet), else `ok`. Chosen over a finer per-tab "has this tab's stage run yet" rule because `last_pipeline_stage` is overwritten to a single terminal value on stop (decision #2 above) and loses which stage it actually reached — a coarser, always-consistent status-based rule was preferred over silently wrong "ok" states for tabs a stopped pipeline never reached. Logged as the spec's suggested example rule, generic (no persona special-casing). |
| 7 | Decision | Default tab | First tab (fixed order: borrowers, housing, credit, assets, property, pricing, send — matches `ApplicationTab` enum order) with `state == flagged`; else `pricing` when `application.status` is `priced`/`sent`/`viewed`/`option_selected`/`inquiry`/`stale` ("≥ Priced"); else `borrowers`. |
| 8 | Decision | Status PATCH validation | `status` is a `Literal[ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED]` on the request schema, so FastAPI/Pydantic 422s any other value natively (AC6) with no extra code. A PATCH on an application already in a terminal status (`withdrawn`/`closed`) 409s (`ConflictError`) — not spec'd explicitly, but "from any non-terminal status" implies the source status must be non-terminal. |
| 9 | Decision | Response shape reuse | `PATCH .../status` returns the same `ApplicationSummaryResponse` as `GET .../summary` (status pill + everything else refreshes from one response), rather than a bespoke shape. |

No big gaps found against spec.md; proceeding.

## Why

Every other LO screen in P3/P5 mounts inside this workspace shell (spec.md "Goal"). It needs one summary endpoint the header/tab rail can poll, a status-change endpoint, and the Next.js shell (sticky header, tab rail, actions menu, pipeline banner) that CQ-017–019/028 will each add one tab's content to.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend summary/status feature | `backend/app/features/applications/summary/{__init__.py,router.py,schemas.py,service.py,tests/}` (new) |
| Pipeline stage writes | `backend/app/workflows/constants.py` (new `PipelineStage`), `backend/app/workflows/activities.py` (stage writes) |
| Router registration | `backend/app/core/registry.py` |
| api-client | `packages/api-client/*` (regenerated, `make api-client`) |
| Overlay focus trap | `packages/ui/src/Overlay.tsx` (+ its test) |
| LO console shell | `apps/lo-console/src/app/applications/[id]/**`, `apps/lo-console/src/features/workspace/**` |
| E2E | `e2e/lo-console/workspace.spec.ts` |
| Docs | this file, `post-dev.md`, `evidence/`, `docs/backlog/README.md` row |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | `PipelineStage` + stage writes in pipeline activities | — | `workflows/constants.py`, `workflows/activities.py` | `workflows/tests/test_activity_events_sequence.py` (extended), new `test_pipeline_stage_writes.py` |
| T2 | Summary schemas + service (header numbers, tab states, default tab) | T1 (reads `last_pipeline_stage`) | `applications/summary/{schemas,service}.py` | `applications/summary/tests/test_service.py` |
| T3 | Summary + status routes | T2 | `applications/summary/router.py`, `core/registry.py` | `applications/summary/tests/test_router.py` |
| T4 | api-client regen | T3 | `packages/api-client/*` | n/a (generated) |
| T5 | Overlay focus trap | — | `packages/ui/src/Overlay.tsx` | `Overlay.test.tsx` |
| T6 | Workspace shell (layout, header, tab rail, actions menu, banner, 404/403 pages, loading skeleton) | T4, T5 | `apps/lo-console/src/app/applications/[id]/**`, `src/features/workspace/**` | Vitest component tests |
| T7 | E2E workspace spec | T6, running stack | `e2e/lo-console/workspace.spec.ts` | `make e2e` |

## Wave schedule (stage 3)

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | T1, T2, T3, T4 | Contract (API + api-client) before any UI consumes it |
| 2 | T5 | Independent of the summary API; needed before T6 dialogs |
| 3 | T6 | Consumes T4 + T5 |
| 4 | T7 | Needs the running stack |

Single-worker execution (no parallel subagents dispatched for this unit — small enough for one context).

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_summary_matches_engine` (parametrized over personas via seed fixtures) |
| AC2, AC3 | `ApplicationHeader.test.tsx` |
| AC4 | `test_tab_states_flags` (API) + `TabRail.test.tsx` (component) + `default_tab` assertions in `test_service.py` |
| AC5 | `test_summary_access_by_role` |
| AC6 | `test_status_patch_terminal_only` |
| AC7 | `test_pipeline_stage_writes.py` (Temporal test env) + `workspace.spec.ts` banner check |
| AC8 | `npx react-doctor -y --blocking error` + `evidence/header-1280.png`, `evidence/header-1440.png` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
