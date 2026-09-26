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
| AC3 | Met | `test_mark_stale_clock_boundaries`: Marcus sent at T; T+20d → `StaleResult()` and still Sent; T+22d → Stale, `expired_at` set, `GET /portal/reports/{token}` under `CLOCK_NOW` → `header.expired = true`. E2E with the API on `CLOCK_NOW`: seed+20d → `applications_marked_stale: 0` (only Luis's quotes flagged, because his version expired); seed+22d → 6 priced personas Stale, and a repeat gives 0. **U3 (P5/P6 merge), through the real CQ-020 path:** `quotes/delivery/tests/test_send_clock.py::test_send_under_clock_now_then_mark_stale_at_20_and_22_days`. `CLOCK_NOW` is set 100 days ahead of the real clock. Marcus is re-priced (`priced_at` = `CLOCK_NOW`) and sent via `POST /packages/{id}/send` plus the `SendQuotePackage` workflow. The version's `sent_at` = `CLOCK_NOW` and `expires_at` = `CLOCK_NOW` + 21 d. At +20 d, `mark_stale(clock.now())` returns `StaleResult()` and he stays Sent; at +22 d he is Stale and the version is expired. |
| AC4 | Met | `test_option_selected_keeps_status` (Luis). E2E at +22d: `luis.romero@…\|option_selected`. |
| AC5 | Met (U3, P5/P6 merge) | `test_reprice_clears_stale` now goes through CQ-018's real `POST /applications/{id}/reprice`. Grace is Stale; the re-price leaves her Priced, with a fresh `priced_at` and cleared stale flags on every quote it refreshed, and one `application.repriced_from_stale` event. The next `mark_stale` run returns `StaleResult()`. `test_autoquote_clears_stale` covers Save & AutoQuote. `reprice_application` and `autoquote_replacing` call `clear_stale(db, app_id, fresh_quote_ids=…)` before the commit, under their quotes → packages → application locks. `test_lock_order.py::test_mark_stale_holding_its_locks_then_reprice_does_not_deadlock` shows the cross-lane end state (Stale → Priced). The original fixture test is kept as `test_pipeline_reprice_then_clear_stale`. The `CLOCK_NOW` re-price works because `priced_at` now reads `core/clock.now()` (plan.md #15 resolved). Details: `docs/backlog/phase-p5-p6-stale-clock.md`. |
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

(Fixed in review round 1; see "Review round 1" below. The original note follows.) The workflow tests (`backend/app/workflows/tests`) had a **pre-existing** intermittent failure under machine load: asyncpg `another operation is in progress` in the persona pipeline tests. I reproduced it on the baseline `worker.py` without the CQ-030 test files: 1 of 4 runs had 21 failures, and the other 3 passed 36/36. The same directory passes when re-run. It is not caused by this item. A single `make test` run under load showed the same cascade (the first teardown fails in `test_marcus_hale_str_tampa_fl_prices`, and the rolled-back connection then fails every later test). The split runs above were green.

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| Medium | A set recommended quote alone decided staleness, so a re-price adding new quotes flipped the application back to Stale | Fixed: the newest `priced_at` decides. Test `test_newer_quotes_outrank_an_old_recommended_quote` |
| Low | `clear_stale` has no caller until CQ-018 | Known (H2); AC5 marked pending, E12 comment on CQ-018 |
| Low | The report's Sent → Viewed ORM write could overwrite a concurrently committed Stale | Fixed: conditional UPDATE. Test `test_first_report_view_does_not_overwrite_stale` |

## Review round 1

Stage-6 findings on PR #17, fixed by a fresh worker. Each fix was written test first.

| ID | Severity | Finding | Resolution | Evidence |
| --- | --- | --- | --- | --- |
| M1a | Major | Re-price did not hold under `CLOCK_NOW`: `clear_stale` cleared by a `priced_at` time window | `clear_stale(db, application_id, *, fresh_quote_ids, now=None) -> bool` now clears only the given ids (other applications' ids are ignored) and moves Stale → Priced when at least one fresh quote belongs to the application. The contract is in the docstring (n4) | `test_reprice_clears_stale`, `test_clear_stale_uses_fresh_ids_not_a_time_window`, `test_clear_stale_without_fresh_quotes_keeps_stale` |
| M1b | Major (follow-up) | Pricing's `priced_at` and send's `sent_at` read `datetime.now(UTC)` | Not edited here (P3 lane: CQ-017/018/020). Logged as plan.md #15. Kaneo comments posted on CQ-018 (with the new `clear_stale` signature) and CQ-020. Until they land, `CLOCK_NOW` demos cannot re-price | Kaneo comments `ztqcurcfjl0hib9vvsosvygq`, `g5ackmz9zq61b0ldu29x7ycc` |
| M2 | Major | Unbounded retries and no run timeout | `STALE_RETRY_POLICY` (3 attempts, modelled on `IMPORT_ENRICH_RETRY_POLICY`) on both activities; the schedule action's `execution_timeout` is 90% of the interval; `catchup_window` equals the interval | `test_stale_retry_policy_is_bounded`, `test_failing_stale_run_gives_up_after_bounded_attempts` (3 calls, then the workflow fails), `test_schedule_policy_bounds_each_run` |
| n1 | Nit | `_matches` ignored the overlap policy | `_matches` compares the overlap policy, catch-up window and run timeout, so older schedules are updated in place | `test_matches_rejects_a_different_policy[×2]`, `test_matches_rejects_a_missing_execution_timeout`, `test_existing_schedule_with_old_policy_is_corrected` (dev server) |
| m1 | Minor | A schedule registration failure stopped the worker | `worker.run_worker` wraps `register_schedules` in `try/except` with `logger.exception` | `test_schedule_registration_failure_does_not_stop_the_worker` |
| m2 | Minor | Decisions raced concurrent writers; `from_status` came from a possibly stale ORM copy | Candidates are read `SELECT … FOR UPDATE` (ordered by id, `populate_existing`), and the decision and `from_status` come from the locked row. Lock order is quotes → versions → applications, which is deadlock-free against the portal paths (plan.md #17) | `test_candidates_are_locked_and_from_status_read_from_the_row` |
| m3 | Minor | The time-window clear could unflag quotes the re-price never touched | Fixed by M1a | `test_clear_stale_uses_fresh_ids_not_a_time_window` |
| m4 | Minor | A Sent/Viewed application re-priced but not re-sent stays non-Stale until its version expires | Accepted gap, plan.md #16 | — |
| m5 | Minor | The version-expired path flagged every quote, including fresh ones | `mark_application_quotes_stale(..., older_than=cutoff, quote_ids=<latest version snapshot ids>)` flags only `priced_at < cutoff OR id = ANY(version quote ids)` | `test_version_expired_flags_only_sent_or_old_quotes` |
| n4 | Nit | The `clear_stale` contract was undocumented for CQ-018 | Docstring in `quotes/stale/service.py` | — |
| Flake | — | Shared workflow-test flake (asyncpg "another operation is in progress", then a cascade) | Test-only fix in `workflows/tests/conftest.py`: a per-test `db_lock` around activity sessions and `wait_for_status`; a per-test worker that drains while holding the lock before `db_session` rolls back; a client interceptor so teardown terminates the workflows each test started; `DEFAULT_RETRY_POLICY` capped at 2 attempts in tests (plan.md #20). No production change | `test_default_retries_are_bounded_in_tests`, `test_activity_sessions_hold_the_test_lock`; three green `make test` runs in a row (below) |

Round-1 self-review (`/code-review`) on the fixes:

| Severity | Finding | Resolution |
| --- | --- | --- |
| Low | Step 3 locked the applications and then updated their quotes, so the stated quotes-before-applications order did not hold | Fixed: `FOR UPDATE OF quotes` on every candidate's quotes before the application lock. `test_candidates_are_locked_and_from_status_read_from_the_row` asserts the order |
| Low | A quote refreshed **in place** (same id) under an expired version is flagged again on the next run | Accepted gap at first, plan.md #17a. **Resolved in U3**: CQ-019's `apply_send_fixture` now back-dates the sent quotes' `priced_at` to `sent_at`, so the guard no longer breaks AC1. The expired version's ids now flag only quotes with `priced_at <= version.sent_at` (`mark_application_quotes_stale(..., priced_by=sent_at)`). Covered by `test_in_place_reprice_under_an_expired_version_is_not_reflagged` (Luis, `CLOCK_NOW`), which fails without the guard |

### Round-1 verification

| Check | Result |
| --- | --- |
| `make lint` | exit 0 (ruff, format, mypy, eslint, tsc, prettier) |
| `make test` ×3 in a row, final code (backend 527 incl. workflows, seed 32, api-client 2, ui 163, lo-console 60, borrower-portal 95) | 3/3 green, all exit 0: backend 527 passed each run, seed 32, frontend all passed |
| Before the self-review fix: `make test` ×3 in a row | 3/3 green (backend 527 passed each run) |
| Slot-16 E2E | `make demo-reset`; `make worker` logged `Created Temporal schedule 'stale-quote-check-cq-s16' (every 1:00:00, task queue 'cq-s16')`. After a restart it logged `already registered; unchanged`. `list_schedules` → exactly one `stale-quote-check-cq-s16`, every 1h, overlap SKIP, catch-up 1h, run timeout 0:54:00. Admin `POST /api/v1/admin/jobs/stale-check` → `{"quotes_marked_stale":3,"versions_expired":1,"applications_marked_stale":1,…}`; DB `grace.kim@…\|stale\|1`. The second call returned all zeros and `application_ids: []`. The worker and API were then stopped and the slot-16 schedule deleted (`count 0`). |

## How to test manually

1. `source scripts/worktree-env.sh 16` (bash), then `make demo-reset`.
2. `make worker`. The log shows the schedule created. Restart it and the log shows "unchanged".
3. `uv run uvicorn app.main:app --port 8116`, log in as `riley.admin@clearquote-demo.test`, then `curl -X POST -b jar localhost:8116/api/v1/admin/jobs/stale-check` twice.
4. Restart the API with `CLOCK_NOW=<seed+22d>` and call it again. The priced personas go Stale; Luis stays OptionSelected.

## Follow-ups

- ~~CQ-018: `/reprice` must call `clear_stale`~~ Done in U3 (P5/P6 merge). `reprice_application` and `autoquote_replacing` call it. Re-price still refreshes Par/Buydown in place (ids stay stable for packages and the recommendation), and #17a is resolved on the job side instead.
- ~~E2: `priced_at` / `sent_at` on `core/clock.now()`~~ Done in U3 (merge plan M5). `priced_at`, `sent_at`, `expires_at`, readiness, report and action expiry, and the letter date all read the clock.
- ~~CQ-017 merge: reconcile its stale marking with `mark_application_quotes_stale`~~ Done in U3 (M4). The private helper was removed; CQ-017 and CQ-018 call the shared helper, and each call site writes one event with a `message`.
- CQ-029: un-hide the admin "Run stale check now" button (`POST /api/v1/admin/jobs/stale-check`).
- CQ-025: the stale list can query `quote_package_versions.expired_at` and `applications.status = stale`.
