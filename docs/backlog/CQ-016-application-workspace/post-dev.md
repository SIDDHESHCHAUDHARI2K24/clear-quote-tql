# CQ-016 — Post-development notes

## Summary

Built `GET /applications/{id}/summary` and `PATCH /applications/{id}/status` (`backend/app/features/applications/summary/`), pipeline-stage instrumentation in the Temporal pipeline activities (`PipelineStage` in `workflows/constants.py`, written by `workflows/activities.py`), and the LO Console's `/applications/[id]/**` workspace shell (`apps/lo-console/src/features/workspace/` + the route tree) — sticky header with the 7 header numbers, a tab rail with ok/flagged/pending states, a withdraw/close actions menu, a 3s-polling pipeline banner, and loading/not-found/error states. Also fixed `packages/ui`'s `Overlay` focus-trap gap (CQ-005) and found+fixed a real bug in it while wiring up the actions menu's confirm dialog.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| AC5: "gets 403 from the API and the 403 page in the UI" | 404, and a single "not found or no access" page (no separate 403 page) | plan.md decision #1 / phase-p3-p4-plan.md D6: `get_scoped_application` already 404s an out-of-scope application (Decision #11), and the backend never returns 403 for a scope violation (401 is for "not signed in", handled by `middleware.ts`'s redirect). Building a 403 page would be dead code. |
| "purchasing power" header number | `ScenarioInputs.purchase_price` of the application's *current scenario* (recommended quote's scenario, else the latest scenario, else null) | No purchasing-power engine exists anywhere in the codebase (`pricing/scenarios/service.py::_purchase_price`'s own "Decision 7"); this follows the same existing convention rather than inventing one. |
| "down payment ($)" | Computed as `purchase_price * down_payment_pct` (`ROUND_HALF_UP` to cents) directly in `applications/summary/service.py`, not read from `QuoteComputation` | Coordinator instruction (mid-task): CQ-021 was concurrently adding `down_payment_amount` to `QuoteComputation`, and this item's owned files exclude `pricing/engine/`. Deriving it straight from the scenario's stored `ScenarioInputs` needs no engine change at all and matches the (now-merged) engine's own formula/rounding exactly — no follow-up needed even though CQ-021's PR #4 has since merged. |
| Tab state rule ("pick a clear rule... log it") | `flagged` (with count) if any open flag on that tab; else `pending` only while `application.status == INTAKE`; else `ok` | plan.md decision #6. A finer "has this tab's pipeline stage run yet" rule was tried first but rejected: on a stopped pipeline, `last_pipeline_stage` is overwritten with a single terminal value (`needs_attention`/`priced`) that loses which stage it actually reached (see D7 below), so a per-tab "stage reached" check would silently show `ok` for tabs a stopped pipeline never got to evaluate. The coarser status-based rule is always correct, if less granular. |
| D7 "last_pipeline_stage... a terminal value when done or stopped" | 6 running-stage names (`importing`…`drafting_quotes`) written at the start of each activity; on stop/finish, overwritten with the `ApplicationStatus` string it lands on (`needs_attention` or `priced`) instead of inventing 2 more names | Reuses the existing status vocabulary instead of a parallel one; `is_pipeline_stage_terminal` (backend) and its frontend mirror (`features/workspace/pipeline.ts`) are the single source of truth for what counts as terminal. Documented in `workflows/constants.py`. |
| `packages/ui` edits "kept to Overlay and new files" | Also added one small case to `Tabs.tsx`'s `TabStatusMark` (a grey dot for `status: "pending"`) | AC4/spec.md's tab rail explicitly requires a grey dot for pending tabs; `Tabs` already had the `"pending"` status value wired into its type/tests but rendered nothing for it. A one-branch, additive, backward-compatible fix — logged here per the instruction to keep `packages/ui` edits minimal to limit conflict risk with CQ-021 (no conflicts occurred). |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `backend/app/features/applications/summary/tests/test_service.py::test_summary_matches_engine_purchasing_power_and_down_payment` computes the expected purchasing power / down payment %/$ independently and compares; `test_summary_no_scenario_yet_numbers_are_null` covers the no-scenario case (e.g. Aisha before pricing). Confirmed against real seed data: `curl .../summary` for Marcus Hale returned `purchasing_power: "342000.00"`, `down_payment_amount: "85500.00"` (25% of 342000, correct). |
| AC2 | Met | `apps/lo-console/src/features/workspace/ApplicationHeader.test.tsx` ("Priya Nair (primary): no PPP field" / "Marcus Hale (STR): shows PPP and the recommended quote's rate"); e2e `workspace.spec.ts` "AC2: Priya Nair (primary) opens on Pricing with no PPP field" against real seed data. |
| AC3 | Met (via fixture, per the spec's own note) | `test_note_rate_null_without_recommended_quote` / `test_note_rate_is_the_recommended_quotes_rate` (unit, with a fixture that sets `recommended_quote_id`) and `ApplicationHeader.test.tsx`'s "7.500%" case. Real seed data never has a recommended quote yet (CQ-018 not built), so every persona's live note rate is "—" today — confirmed via `curl`, matches AC3's null case exactly as specified ("For AC3, test with a fixture that sets it"). |
| AC4 | Met | `test_tab_states_flags`, `test_default_tab_first_flagged_wins_over_pricing` (API); `TabRail.test.tsx` (component); e2e `workspace.spec.ts`'s two AC4 tests against real seed data — confirmed Aisha Coleman opens on Pricing (flagged, missing-occupancy OB-required-field flag lands there) with a red badge, and Ben Ford opens on Housing (housing-history-under-24-months flag) with a red badge. |
| AC5 | Met (404, not 403 — see Deviations) | `test_summary_access_by_role`, `test_status_patch_404_for_other_los_application` (API); e2e "AC5" test against real seed data — Jordan Lee gets the not-found page for Ben Ford (owned by the other seeded LO), Casey Nguyen (Manager) opens it fine. |
| AC6 | Met | `test_status_patch_terminal_only` (API, 422 for `"priced"`, 200 for `"withdrawn"`); `StatusActionsMenu.test.tsx` (dialog, reason field, error handling); e2e "AC6" test — confirmed real withdraw flow end to end (status pill flips to "Withdrawn", Actions menu disappears). |
| AC7 | Met | `backend/app/workflows/tests/test_pipeline_stage_writes.py` (Temporal test env, both the happy-path-to-`priced` and flagged-path-to-`needs_attention` personas); `PipelineBanner.test.tsx`; e2e "AC7" test — triggered `POST .../pipeline/start` for Marcus Hale against the real worker and confirmed the banner renders "Pipeline running: Importing". Known limitation: re-importing an *already-seeded* persona's `application_parties` etc. hits a unique-constraint conflict in `import_from_los` (pre-existing, outside this item's owned files — `applications/service.py`), so the workflow never reaches `priced` for a persona re-import specifically; the "reaches terminal and the banner disappears" half of AC7 is proven by the backend Temporal test (which uses a persona built from scratch, the realistic "first import" case) rather than re-demonstrated live in the UI against already-seeded data. |
| AC8 | Met | `npx react-doctor -y --blocking error` exits 0 (score 81/100, only warnings — see Test log); screenshots `evidence/header-1280.png` and `evidence/header-1440.png` (header stays visible after scrolling, both widths). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend -q` | 385 passed |
| Seed tests | `uv run pytest seed -q` | 27 passed |
| ruff / mypy | `make lint` (backend portion) | clean |
| Frontend tests | `pnpm -r run test` | 111 (packages/ui) + 2 (api-client) + 34 (lo-console) + 37 (borrower-portal) passed |
| eslint / tsc / prettier | `make lint` | clean |
| E2E typecheck | `pnpm exec tsc --noEmit -p tsconfig.json` | clean |
| react-doctor | `npx react-doctor -y --blocking error` | exit 0, score 81/100 (Needs work — only warnings, all pre-existing classes or out of this item's owned files; see Follow-ups) |
| `alembic heads` | `uv run alembic heads` | `bbd0e3150264 (head)` — one head, no new migration added |
| `make demo-reset` | `time make demo-reset` | ~1.1–1.2s |
| E2E (slot 3, full recipe) | `LO_BASE_URL=http://localhost:3103 PORTAL_BASE_URL=http://localhost:3203 SEED_STAFF_PASSWORD=<slot 3's> pnpm exec playwright test e2e/lo-console --workers=1` (against a fresh `make demo-reset`, the API on 8103, the worker on `cq-s3`, LO console on 3103) | 11 passed: both smoke/report-gallery specs, `staff-login.spec.ts`, and all 7 of `workspace.spec.ts`'s AC-named tests |

## Review findings (stage 6)

No fresh-subagent review was dispatched for this run (single-context execution). Self-review via `code-review`-equivalent scrutiny during development found and fixed one real bug (see below); no other findings open.

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major (self-found while writing `StatusActionsMenu.test.tsx`) | `Overlay`'s focus-trap effect was keyed on `[isOpen, onClose]`. Any parent re-render producing a new `onClose` closure (e.g. every keystroke updating local `reason` state) tore the effect down and rebuilt it, which re-stole focus to the dialog's first focusable element (often a button) on every keystroke. A later typed space then "clicked" that focused button, closing the dialog mid-typing. | Split into two effects: initial-focus/return-focus keyed only on `isOpen`; Escape/Tab-trap keyed on `[isOpen, onClose]` (no focus side effect, safe to re-attach). Regression test added to `Overlay.test.tsx` ("does not steal focus back to the first element while typing, even when onClose is a new closure every render"). |
| Minor | `StatusActionsMenu.confirm()` reset `submitting` outside a `finally` (react-doctor `no-loading-flag-reset-outside-finally`) | Wrapped in try/finally. |
| Minor | `WorkspaceProvider`'s context value object was reconstructed every render (react-doctor `jsx-no-constructed-context-values`) | Wrapped in `useMemo`. |

## How to test manually

1. `source scripts/worktree-env.sh 3` (or your own slot).
2. `uv run alembic upgrade head && make demo-reset`.
3. In the background: `uv run uvicorn app.main:app --app-dir backend --port <API_PORT>`, `uv run python -m app.workflows.worker` (from the repo root — `Settings.env_file` is relative to cwd), `pnpm --filter @cq/lo-console exec next dev -p <LO_PORT>`.
4. Sign in as `jordan.lee@clearquote-demo.test` (password: `.env`'s `SEED_STAFF_PASSWORD`).
5. Open Aisha Coleman's application (look up her id: `docker compose -f infra/docker-compose.yml exec postgres psql -U cq -d <db> -tAc "select a.id from applications a join clients c on c.id=a.client_id where c.email='aisha.coleman@clearquote-demo.test';"`, then visit `/applications/<id>`) — lands on Pricing with a red badge.
6. Open Priya Nair's application — lands on Pricing, no PPP field.
7. Click Actions → Withdraw application → confirm — status pill flips to "Withdrawn", Actions menu disappears.
8. `POST /api/v1/applications/<id>/pipeline/start` for a persona, then reload its workspace — "Pipeline running: Importing" banner appears (see the AC7 known-limitation note above for why it won't reach "priced" for an already-seeded persona specifically).

## Follow-ups

- CQ-017/018/019/028 replace the placeholder tab pages (`"Built in CQ-0XX."`) with real content — no other change needed to the shell; a new tab page is just `apps/lo-console/src/app/applications/[id]/<tab>/page.tsx` reading `useWorkspace()` for the current summary/application id.
- `react-doctor`'s remaining warnings (score 81/100): 5× "client-side redirect for navigation" (`src/app/page.tsx` ×4, pre-existing from CQ-005; `DefaultTabRedirect.tsx` ×1, same class — a client-fetched `default_tab` genuinely can't be a server redirect without also fetching the summary server-side, which is out of this item's scope); "all state reset on prop change" (`WorkspaceProvider.tsx`, intentional — a new `applicationId` is a genuinely new resource); "custom modal instead of dialog" (`Overlay.tsx`, pre-existing div-based modal design, out of scope to redesign here). None are errors; `--blocking error` passes (exit 0).
- The seeded LO email for e2e is `jordan.lee@clearquote-demo.test` (not `lo@clearquote.test` — see `phase-p3-p4-foundation.md`'s own deviation note, reused here).
- Running `workspace.spec.ts` together with other real-login specs in the same `pnpm exec playwright test` invocation can trip the staff login endpoint's shared Valkey rate limit across files if they schedule concurrently; ran cleanly with `--workers=1` from a fresh `make demo-reset`. `workspace.spec.ts` itself flushes its own worktree's Valkey db between its own tests (`flushLoginRateLimit`, `e2e/helpers/db.ts`) so it's self-contained when run alone.
