# CQ-030 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Expired state for sent versions | Decided: nullable `quote_package_versions.expired_at` (migration off `3b55187d53d7`, one head). `mark_stale` sets it once to the run's `now`, which makes "expired" queryable and keeps the step idempotent. The CQ-022 report still computes `expired` from `expires_at` at request time. |
| 2 | Decision | Seeded quotes are priced at seed time, not at send time | `make demo-reset` prices Grace Kim now and back-dates only her send (25 days ago). The trigger for her application is therefore the expired sent version. When an application moves to Stale, `mark_application_quotes_stale` flags **all** its quotes, so AC1 ("her quote stale") holds without touching the seed. |
| 3 | Decision | Which quote decides the application | The newest `priced_at` among the application's quotes. That is never older than the recommended quote's, so a re-price that adds quotes without repointing `recommended_quote_id` cannot flip the application back to Stale (a stage-6 review finding; the first draft used the recommended quote alone). The rule is age-based (`priced_at < now − stale_days`), not based on the `stale` flag, so a CQ-017 input-override stale flag does not move the status to Stale with the wrong message. |
| 4 | Decision | Which applications check the sent version | Only Sent and Viewed. A Priced application after a re-price has an old, expired version by design, and it must not flip back to Stale (that would break AC5 and idempotency). Priced uses the quote rule only. |
| 5 | Decision | Inquiry and OptionSelected | Status kept (AC4). Their quotes are flagged by the age rule (step 1). If their latest sent version has expired, their quotes are also flagged through `mark_application_quotes_stale`. No activity event is written. |
| 6 | Decision | Activity event | `type="application.stale"`, `actor="system"`, payload `{"message": "Quotes older than {stale_days} days", "from_status", "reason": "quote_age" or "version_expired"}`, `at=now`. It is written only when the conditional status UPDATE actually changed the row. |
| 7 | Decision | `stale_quote_days` | Read from the `settings` table. The default is 21 when the row is missing. The boundary is strict: stale only when age > stale_days. |
| 8 | Decision | `now` inside Temporal | `StaleQuoteCheckWorkflow(now_iso=None)`. When no `now` is given (the schedule case), it runs the tiny activity `resolve_clock_now` (which returns `core/clock.now()`, honouring `CLOCK_NOW` in the worker process). It then passes the result to `mark_stale_activity(now_iso)`. The mark activity never reads the clock. |
| 9 | Decision | Schedule id per task queue | Slots share one Temporal namespace. The id is `stale-quote-check` on the default queue `clear-quote-pipeline`, and `stale-quote-check-<queue>` on any other queue, so one slot's worker never rewrites another slot's schedule. Registration is describe → create if missing → update only if the interval or queue differs. A lost create race (`ScheduleAlreadyRunningError`) falls through to the update check. Overlap policy SKIP. |
| 10 | Decision | `clear_stale(db, application_id, *, now=None)` | Clears `stale` on the application's quotes priced within the window (the fresh ones a re-price just wrote or updated). It moves Stale → Priced and writes the event `application.repriced_from_stale`. Old superseded quotes keep their flag, so a later run changes nothing. |
| 11 | Decision (small necessity outside owned files) | `quote_package_versions.expired_at` | Added the column to `quotes/send/models.py` (one mapped column) to match the migration. |
| 12 | Decision (small necessity outside owned files) | Report `expired` under `CLOCK_NOW` | `portal/reports/service.py` read `datetime.now(UTC)`. It now reads `core/clock.now()` (a one-line change, E2), so AC3's "his report shows expired" works with `CLOCK_NOW` in demos. Behaviour is identical when `CLOCK_NOW` is unset. |
| 13 | Follow-up (H2/E12) | CQ-017's own stale marking in `pricing/enrichment/service.py` | Not merged here. CQ-030 owns `mark_application_quotes_stale`, and the orchestrator reconciles it when CQ-017 merges. CQ-018's `/reprice` must call `clear_stale`. AC5 is therefore `pending — re-check after CQ-018`. |
| 14 | Decision | `interval` setting | `Settings.stale_check_interval_seconds` (env `STALE_CHECK_INTERVAL_SECONDS`, default 3600; 60 allowed for demos). |

No big gaps.

## Why

Rates move, so a quote older than 21 days must not be presented as current. The job makes staleness a real application status the dashboard (CQ-025) and the re-price flow (CQ-018) can act on.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Migration | `alembic/versions/<rev>_quote_package_versions_expired_at.py` (create); `backend/app/features/quotes/send/models.py` (+1 column) |
| Service | `backend/app/features/quotes/stale/{__init__,service,schemas}.py` + `tests/` |
| Temporal | `backend/app/workflows/stale_quote_check.py`, `backend/app/workflows/stale_schedule.py`, `backend/app/workflows/worker.py` (registration), `backend/app/workflows/tests/test_stale_*.py` |
| Admin API | `backend/app/features/admin/__init__.py` (empty, if missing), `backend/app/features/admin/jobs/{__init__,router,schemas}.py` + `tests/`; one line in `core/registry.py` |
| Report clock | `backend/app/features/portal/reports/service.py` (clock.now) |
| Client | `packages/api-client` regenerated |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Migration + model column | — | alembic, send/models.py | alembic heads = 1 |
| T2 | `mark_stale`, `mark_application_quotes_stale`, `clear_stale` | T1 | quotes/stale/** | AC1–AC5 service tests |
| T3 | Workflow, activities, schedule registration, worker wiring | T2 | workflows/stale_*.py, worker.py | AC6, workflow run test |
| T4 | Admin endpoint + registry + api-client | T2 | admin/jobs/**, registry line, api-client | AC7 |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1 | Schema first |
| 2 | T2 | Service before callers |
| 3 | T3, T4 | Disjoint files |

Small item: run inline by one worker.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `quotes/stale/tests/test_service.py::test_mark_stale_grace_kim` |
| AC2 | `test_mark_stale_idempotent` |
| AC3 | `test_mark_stale_clock_boundaries` (+ report `expired` via `/portal/reports/{token}` with `CLOCK_NOW`) |
| AC4 | `test_option_selected_keeps_status` |
| AC5 | `test_reprice_clears_stale` (auto_price + `clear_stale`; pending — re-check after CQ-018) |
| AC6 | `workflows/tests/test_stale_schedule.py::test_schedule_registered_once` (Temporal dev server via `WorkflowEnvironment.start_local`) |
| AC7 | `admin/jobs/tests/test_router.py::test_admin_stale_check_endpoint` (+ 403 for LO and Manager) |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
