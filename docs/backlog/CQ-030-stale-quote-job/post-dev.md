# CQ-030 — Post-development notes

## Summary

`quotes/stale/service.py` holds the idempotent job body `mark_stale(db, now)`. It flags quotes older than `stale_quote_days` (settings, default 21, strict), stamps a new `quote_package_versions.expired_at` on sent versions past `expires_at`, and moves Priced/Sent/Viewed applications to Stale with one `application.stale` event ("Quotes older than 21 days"). Inquiry/OptionSelected keep their status but their quotes are flagged. The service also exposes the shared helper `mark_application_quotes_stale` (E12) and the re-price hook `clear_stale` (Stale → Priced) for CQ-018. A Temporal workflow `StaleQuoteCheckWorkflow` runs it; the worker registers the Schedule `stale-quote-check` idempotently at startup. `POST /api/v1/admin/jobs/stale-check` (Admin only) runs the same service at `core/clock.now()` and returns the counts.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| "recommended quote … is stale" decides the application | The newest `priced_at` among the application's quotes decides (never older than the recommended quote's) | Review finding: a re-price that adds new quotes without repointing `recommended_quote_id` would otherwise flip the application back to Stale every run (plan.md #3). |
| Sent version check for Priced/Sent/Viewed | Version check only for Sent/Viewed; Priced uses quote age | A re-priced (Priced) application keeps its old, expired send by design; checking it would undo AC5 (plan.md #4). |
| Schedule id `stale-quote-check` | `stale-quote-check` on the default queue `clear-quote-pipeline`; `stale-quote-check-<queue>` on per-slot queues | Worktree slots share one Temporal namespace (plan.md #9). |
| Re-price via CQ-018 `/reprice` | `clear_stale(db, application_id)` hook; AC5 tested with the pipeline's pricing stage (`run_pricing_stage`) + `clear_stale` | CQ-018 not built yet (H2). |

Small edits outside owned files (logged in plan.md #11, #12):
- `quotes/send/models.py`: added the `expired_at` column.
- `portal/reports/service.py`: two changes. It reads `core/clock.now()` so `CLOCK_NOW` shows the report as expired. Its Sent → Viewed write is now a conditional UPDATE, so it cannot overwrite a Stale status the job committed at the same moment (review finding).

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence (test name, command output, screenshot path) |
| --- | --- | --- |
| AC1 | Met | `test_mark_stale_grace_kim`. E2E on slot 16 after `make demo-reset`: `POST /api/v1/admin/jobs/stale-check` → `{"quotes_marked_stale":3,"versions_expired":1,"applications_marked_stale":1,"application_ids":["76d3c0d3-…"]}`. DB check: `grace.kim@…\|stale\|1` (status, count of `application.stale` events). On an earlier reset, the hourly Schedule itself fired at 18:00:00Z and did the same: one event, payload `{"reason":"version_expired","message":"Quotes older than 21 days","from_status":"sent"}`. |
| AC2 | Met | `test_mark_stale_idempotent`; the admin endpoint test runs twice. E2E: second curl → all counts 0, `application_ids: []`. |
| AC3 | Met | `test_mark_stale_clock_boundaries`: Marcus sent at T; T+20d → `StaleResult()` and still Sent; T+22d → Stale, `expired_at` set, `GET /portal/reports/{token}` under `CLOCK_NOW` → `header.expired = true`. E2E with the API on `CLOCK_NOW`: seed+20d → `applications_marked_stale: 0` (only Luis's quotes flagged, because his version expired); seed+22d → 6 priced personas Stale, and a repeat gives 0. |
| AC4 | Met | `test_option_selected_keeps_status` (Luis). E2E at +22d: `luis.romero@…\|option_selected`. |
| AC5 | Met with a fixture — **pending: re-check after CQ-018** | `test_reprice_clears_stale`: Grace Stale → `run_pricing_stage` (pipeline pricing path) → `clear_stale` → Priced, fresh `priced_at`, no stale flags, next run no-op. CQ-018's `/reprice` must call `clear_stale` (E12). |
| AC6 | Met | `test_schedule_registered_once`, `test_schedule_updated_when_interval_changes` (Temporal dev server via `WorkflowEnvironment.start_local`). E2E: the worker log shows `Created Temporal schedule 'stale-quote-check-cq-s16' (every 1:00:00, task queue 'cq-s16')`. After a restart: `already registered; unchanged`. `list_schedules` → exactly `['stale-quote-check-cq-s16']`. |
| AC7 | Met | `test_admin_stale_check_endpoint` (counts, then zeros on repeat), `test_admin_stale_check_forbidden_for_non_admins[lo,manager]` → 403, unauthenticated → 401. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend --ignore backend/app/workflows` + `uv run pytest backend/app/workflows` | 471 passed; 42 passed (includes 7 new CQ-030 Temporal tests) |
| Seed tests | `uv run pytest seed` | 32 passed |
| Lint / types | `make lint` | exit 0 (ruff, format, mypy: no issues in 345 files, eslint, tsc, prettier) |
| Frontend | `pnpm -r run test` | api-client 2, ui 163, lo-console 60, borrower-portal 95: all passed (backend-only item, no frontend changes; react-doctor n/a) |
| Migrations | `uv run alembic heads` | one head `c30a57a1e0d1` |

The workflow tests (`backend/app/workflows/tests`) have a **pre-existing** intermittent failure under machine load: asyncpg `another operation is in progress` in the persona pipeline tests. I reproduced it on the baseline `worker.py` without the CQ-030 test files: 1 of 4 runs had 21 failures, and the other 3 passed 36/36. The same directory passes when re-run. It is not caused by this item. A single `make test` run under load showed the same cascade (the first teardown fails in `test_marcus_hale_str_tampa_fl_prices`, and the rolled-back connection then fails every later test). The split runs above were green.

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| Medium | A set recommended quote alone decided staleness, so a re-price adding new quotes flipped the application back to Stale | Fixed: the newest `priced_at` decides. Test `test_newer_quotes_outrank_an_old_recommended_quote` |
| Low | `clear_stale` has no caller until CQ-018 | Known (H2); AC5 marked pending, E12 comment on CQ-018 |
| Low | The report's Sent → Viewed ORM write could overwrite a concurrently committed Stale | Fixed: conditional UPDATE. Test `test_first_report_view_does_not_overwrite_stale` |

## How to test manually

1. `source scripts/worktree-env.sh 16` (bash), then `make demo-reset`.
2. `make worker`. The log shows the schedule created. Restart it and the log shows "unchanged".
3. `uv run uvicorn app.main:app --port 8116`, log in as `riley.admin@clearquote-demo.test`, then `curl -X POST -b jar localhost:8116/api/v1/admin/jobs/stale-check` twice.
4. Restart the API with `CLOCK_NOW=<seed+22d>` and call it again. The priced personas go Stale; Luis stays OptionSelected.

## Follow-ups

- CQ-018: `/reprice` must call `quotes.stale.service.clear_stale(db, application_id)` and should repoint `applications.recommended_quote_id`.
- CQ-017 merge: reconcile its own stale marking in `pricing/enrichment/service.py` with `mark_application_quotes_stale` (E12).
- CQ-029: un-hide the admin "Run stale check now" button (`POST /api/v1/admin/jobs/stale-check`).
- CQ-025: the stale list can query `quote_package_versions.expired_at` and `applications.status = stale`.
