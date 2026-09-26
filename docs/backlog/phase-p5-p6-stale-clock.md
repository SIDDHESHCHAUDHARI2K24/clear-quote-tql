# U3 (P5/P6 → main merge): one stale path, reprice clears stale, one clock — post-development notes

Branch `p56-stale-clock` → `phase-p5-p6`, on slot 31. This covers merge plan decisions **M4** and **M5** (unit **U3**, `docs/backlog/phase-p5-p6-main-merge-plan.md`) and the review minors carried over from PR #35 (U2).

## Summary

- **One stale path (M4).**
  - `quotes.stale.service.mark_application_quotes_stale` is the only code that flags quotes stale. It now returns the sorted ids it changed instead of a count, because callers log them in their one event.
  - CQ-017 override and revert (`pricing/enrichment/service.py`) and CQ-018 `update_scenario` (`quotes/builder/service.py`) both call it. The private `_mark_application_quotes_stale` and the raw `UPDATE quotes SET stale = true` are gone.
  - Each calling site writes exactly one event per marking, with a human-readable `payload.message`:

    | Site | Event | `message` |
    | --- | --- | --- |
    | CQ-017 override/revert | `quotes.marked_stale` | "Quotes marked stale: property tax annual rate overridden" / "… reverted" |
    | CQ-018 scenario PUT | `scenario.updated` (it already existed; now carries `message` and `quote_ids`) | "Quotes marked stale: scenario inputs changed" |
    | CQ-030 job | `application.stale` (unchanged) | "Quotes older than N days" |
    | CQ-033 FICO bucket | `credit.hard_pull_completed` (unchanged; `quotes_marked_stale` is still a count) | unchanged |

  - `quote.recommended` has a `message` at all three writers (review finding m5): "Recommended Par at 6.625%", "Recommended quote picked for the draft package" and "Recommended quote changed on the Send tab".
  - LO timeline icons: `apps/lo-console/src/features/activity/icons.tsx`. `quotes.marked_stale` maps to flag. `quote.recommended`, `quotes.repriced`, `quote.deleted` and `scenario.*` map to pricing. Before this change they fell back to the generic bullet.
- **Reprice clears stale (CQ-030 AC5).**
  - `reprice_application` and `autoquote_replacing` call `clear_stale(db, application.id, fresh_quote_ids=…)` before the commit. The ids are Par, Buydown and every other quote the re-price refreshed; a quote kept stale because it is no longer offered is excluded.
  - Stale → Priced writes one `application.repriced_from_stale` event.
  - The locks already held are quotes → packages → application (U2), and `clear_stale` only UPDATEs those rows.
  - `autoquote_replacing` re-prices one scenario, so it clears the status only when no other scenario still has stale quotes (code-review fix).
  - The reprice response's `priced_at` now equals the quotes' `priced_at`, because one `clock.now()` is passed into `_reprice_scenario`.
- **Readiness uses the setting.**
  - `send/readiness.py` no longer has `RATE_STALE_DAYS`.
  - `package_blockers` reads `get_stale_quote_days(db)`, the same reader CQ-030's job uses, and `is_rate_stale(quote, now, stale_days)` uses the same strict `>` boundary.
- **One clock (M5).** `core.clock.now()` now replaces `datetime.now(UTC)` / `date.today()` in:

  | Area | Where |
  | --- | --- |
  | `priced_at` | `pricing/scenarios/service.py` (`persist_quote`), `quotes/builder/service.py` (reprice, autoquote) |
  | `sent_at` / `expires_at` | `quotes/delivery/steps.py` (Freeze), `portal/reports/versions.py` (default `sent_at`) |
  | Send | `quotes/send/service.py` (preview `as_of`/`expires_at`, event `at`), `send/readiness.py` |
  | Expiry checks | `portal/actions/service.py` (`expired`), `clients/service.py` (sent-version status); the portal report view already used the clock |
  | Letter | `quotes/pdf/service.py` default letter date |
  | Other business stamps | `applications/verification/service.py` (flag `resolved_at`, summary `as_of`), `pricing/enrichment/service.py` (`overridden_at`) |
  | Event `at` on the P3 side | builder, enrichment, send, delivery `record`, summary PATCH, pipeline activities |

  Workflow code is untouched and still deterministic. `app/workflows/activities.py::_write_event` runs only inside activities. The stale workflow still gets its `now` from the `resolve_clock_now` activity.

  Deliberately left on the real clock:
  - `auth/borrower/service.py` (OTP expiry — security, not business time)
  - `integrations/common/logging.py` (`called_at` of provider calls)
  - `integrations/crm/mock.py` (the mock CRM's own timestamp)
  - the seed loader (outside `backend/app`)

## Decisions

- **Decision: `mark_application_quotes_stale` returns the changed ids, not a count.** CQ-017's event must keep logging `quote_ids`. A second, id-returning helper would have been a second stale path. `mark_stale` and CQ-033 take `len(...)`.
- **Decision: `update_scenario` keeps its `scenario.updated` event as the one event for its stale marking.** It gains `message` and `quote_ids`. A second `quotes.marked_stale` event would break "exactly one event per marking", and the scenario event already names what changed. The marking stays scenario-scoped: the shared helper gets `quote_ids=<that scenario's quotes>`.
- **Decision: CQ-030 #17a resolved rather than accepted.**
  - Reprice updates Par/Buydown in place (ids stay stable), so a refreshed quote stayed in an expired version's snapshot and the next run flagged it again.
  - The `priced_at <= sent_at` guard was rejected in CQ-030 only because the seed priced Grace after her back-dated send. CQ-019's `apply_send_fixture` now back-dates the sent quotes' `priced_at` to the version's `sent_at`, so the guard is safe.
  - The helper's new `priced_by` argument limits the expired-version arm to quotes with `priced_at <= version.sent_at`. The quote-age arm (`priced_at < cutoff`) is unchanged, and AC1–AC4 still pass.
  - For the AC5 path itself the edge never applied: a Priced application is decided by quote age only (CQ-030 #4).
- **Decision: P3 event `at` values use the clock too.** M5 allows the DB default. The P5/P6 events (`events.add_event`, `mark_stale`, `clear_stale`) already used the clock, so mixing both would put a reprice before the stale event it cleared on a `CLOCK_NOW` demo timeline.
- **Decision (review minor a): the step-3 re-lock is limited.** It now covers only applications that were not candidates at step 1. Step 1 now also returns each locked quote's application and status. See the lock doc's follow-ups.

## Acceptance evidence (stage 7)

| Criterion | Evidence |
| --- | --- |
| CQ-030 AC5: Grace Stale → reprice → Priced, fresh `priced_at`, cleared flags | `quotes/stale/tests/test_service.py::test_reprice_clears_stale` (real `POST /applications/{id}/reprice`, one `application.repriced_from_stale` event, next run no-op) and `test_autoquote_clears_stale`. Both fail on the pre-U3 builder (3 of 3 new tests red, checked by swapping in `origin/phase-p5-p6`'s `builder/service.py`). |
| CQ-030 AC3 with `CLOCK_NOW` through the real CQ-020 path | `quotes/delivery/tests/test_send_clock.py::test_send_under_clock_now_then_mark_stale_at_20_and_22_days`. At `CLOCK_NOW` = real + 100 d: the reprice gives `priced_at` = `CLOCK_NOW`; `POST /send` plus the workflow give `sent_at` = `CLOCK_NOW` and `expires_at` = +21 d. At +20 d, `StaleResult()` and still Sent; at +22 d, Stale with the version expired. |
| Override marks stale through the shared helper, one event with a message | `pricing/enrichment/tests/test_stale_marking.py::test_override_uses_the_shared_stale_path_with_one_messaged_event` (spy on the shared helper). Scenario PUT: `quotes/builder/tests/test_review_round1.py::test_scenario_put_marks_stale_through_the_shared_path_with_one_event`. |
| Readiness under `CLOCK_NOW` and the setting | `quotes/send/tests/test_readiness.py::test_readiness_reads_the_clock_and_the_setting`. With 21 days: ready at +20 d, `quotes_stale` at +22 d. With 30 days: ready at +22 d. With 10 days: `quotes_stale` at +15 d. |
| #17a: a re-price in place under an expired version is not re-flagged | `test_in_place_reprice_under_an_expired_version_is_not_reflagged` (Luis, `CLOCK_NOW`). It fails without the `priced_by` guard. |
| Portal expiry on the clock | `portal/actions/tests/test_router.py::test_expiry_reads_the_injected_clock` |
| Minor a: step-3 re-lock | Code change in `mark_stale`. The existing lock and stale suites stay green. |
| Minor b: id ordering proven | `test_lock_order.py::test_mark_stale_locks_its_quotes_by_id_before_updating` asserts `ORDER BY quotes.id FOR NO KEY UPDATE OF quotes` runs before the first `UPDATE quotes`, and keeps the blocking check. |
| Minor c: no fixed pause | `_paused` waits on `_until_another_backend_waits_on_a_lock`, which polls `pg_stat_activity` for `wait_event_type = 'Lock'` in the test DB every 20 ms, with a 10 s bound, and fails loudly on timeout. The lock-order file dropped from about 7 s to about 4.4 s. |
| Minor d: SQL-order assertions | `test_send_tab_writes_lock_packages_before_the_application` (first-load slow path and PUT: packages → application) and `test_action_locks_package_then_version_then_application` (portal). |
| Cross-lane end state | `test_mark_stale_holding_its_locks_then_reprice_does_not_deadlock` now also asserts Priced with one `application.repriced_from_stale` event. |

## Test log (stage 5)

- `make lint`: exit 0 (ruff, mypy with 509 files clean, eslint, tsc, prettier).
- `make test` (final): exit 0. Backend 992 passed (U2 had 981; 11 new tests). Seed 35. api-client 2, ui 163, borrower-portal 156 (1 skipped, pre-existing), lo-console 343 (6 new icon cases).
- Flake check before the review fixes: the stale, builder, send, delivery, portal, lock-order and enrichment suites ran 3 times in a row, 298 passed each time.
- `make demo-reset` on `cq_dev_s31`: exit 0, about 2 s.
- Playwright: see "E2E" below.

## E2E

Slot 31 (API 8131, LO 3131, portal 3231, queue `cq-s31`), after `make demo-reset` with the API and worker restarted. The full Playwright suite (lo-console, borrower-portal and cross-app) ran with `--workers=1 --reporter=line`, with `DATABASE_URL`, `SEED_STAFF_PASSWORD` and `SEED_BORROWER_PASSWORD` exported from `.env` through a small Python wrapper:
- **88 passed, 0 skipped** (2.7 min), on commit 07621b2.
- The later review fixes change only backend branches that no spec exercises (Save & AutoQuote on a multi-scenario Stale application, and event wording). They are covered by pytest.
- The coordinator asked for a single e2e run, so it was not repeated.
- The screenshot churn the suite writes under `docs/backlog/*/evidence` was reverted to `origin/phase-p5-p6`.
- The slot-31 API, worker and both dev servers were stopped afterwards.

## Review findings (stage 6)

`code-review` (medium) on `origin/phase-p5-p6...HEAD`: no high-severity findings.

| Severity | Finding | Resolution |
| --- | --- | --- |
| Low | `autoquote_replacing` cleared a Stale application after re-pricing one scenario while another scenario's (possibly recommended) quotes were still stale. The next job run never re-flagged it, because the deciding quote was now fresh. | Fixed. `clear_stale` runs only when no *other* scenario of the application has stale quotes. The test is `test_autoquote_keeps_stale_while_another_scenario_is_stale`; it failed without the guard. |
| Low | The `quotes.marked_stale` / `scenario.updated` message said "Quotes marked stale" even when no quote changed | Fixed. When nothing changed, the message reads "Property tax annual rate overridden" or "Scenario inputs changed", as asserted in `test_override_with_no_quotes_yet_still_logs_the_change_with_no_quote_ids`. The event is still written (CQ-017 audit trail). |
| Note | A 401 flake in `test_mark_stale_clock_boundaries` during the review | It came from the reviewer's pytest run sharing `cq_test_s31` with my concurrent flake loop, not from the code. It passed in every sequential run. |

**A test-harness race surfaced while verifying.** In full `make test` runs, `delivery/tests/test_send.py::test_letter_pdf_contents` failed with `No completion event found`.
- The root cause is Freeze's first attempt: `savepoint "sa_savepoint_N" does not exist`.
- `start_send` starts the workflow and *then* commits the request session. In the tests, activities share the test connection, so a Freeze that started in that window nested its savepoint inside the request's, and the request's commit released it.
- This does not happen in production: there the activity has its own connection and waits on the package lock.
- The timing shift from the extra settings read in `send_blockers` exposed it.
- Fixed in `delivery/tests/conftest.py`: one `asyncio.Lock` serializes `start_send` and every activity session on the shared connection. After the fix, the full backend ran green twice.

## Follow-ups

- The mid-job status-change edge in `mark_stale` is still accepted (lock doc).
- CQ-016 AC5 (Sent/Viewed re-priced but not re-sent) is unchanged: `clear_stale` still moves only Stale → Priced (CQ-030 #16).

## Review minors (post-merge)

- **Status guard now checks the whole application.** `reprice_application` and `autoquote_replacing` (`quotes/builder/service.py`) only move Stale → Priced through `_application_has_stale_quotes`, which checks every quote on the application -- not `Scenario.id != scenario_id` as before. The old, scenario-scoped check missed the case where `_reprice_scenario` itself leaves the just-repriced scenario's own quote stale (a manual pick whose product left the grid); the application could still flip to Priced with a stale quote sitting on it. Test: `quotes/stale/tests/test_service.py::test_reprice_application_keeps_stale_when_a_quote_stays_stale`.
- **Timeline tiebreak.** `list_activity` and `list_activity_for_applications` (`applications/timeline/service.py`) order by `at DESC, created_at DESC, id DESC`. Under a frozen `CLOCK_NOW` two events can share the same `at` exactly; `created_at DESC` breaks the tie by insertion order, newest first (a random-UUID `id DESC` alone does not). Tests: `applications/timeline/tests/test_router.py::test_activity_tiebreak_is_insertion_order_newest_first` and `applications/timeline/tests/test_service.py::test_tiebreak_is_insertion_order_newest_first`.
- **Seed reads the same clock.** `seed/loader.py` (`seed_borrower_accounts`'s `email_verified_at`, `seed_no_application_borrower`'s `email_verified_at`, `_add_activity_event`'s `at`, `apply_send_fixture`'s `now`/`sent_at`) and `seed/generators/background_applications.py` (`seed_background_applications`'s `now`) call `core.clock.now()` instead of `datetime.now(UTC)`. Under a `CLOCK_NOW` demo, seeded fixtures date themselves relative to the frozen instant, matching whatever the API and worker see. Under the real clock (no `CLOCK_NOW` set, `make demo-reset`'s normal path), `clock.now()` returns `datetime.now(UTC)` exactly, so every persona's end state (statuses, which quotes are stale, which sent versions are expired) is unchanged -- the existing seed suite (`seed/tests/`) still passes as-is.

### Two deliberate exceptions to "one event per stale marking"

The summary above says every stale marking goes through `mark_application_quotes_stale` and gets exactly one event from its caller. Two paths flag a quote `stale = true` outside that helper, on purpose, and neither writes its own event:

1. **`mark_stale` step 1's bulk age UPDATE** (`quotes/stale/service.py`). Before step 3 decides which *applications* move to Stale, step 1 flags every quote past the age cutoff, for every application -- not only the ones whose status changes. A Priced application whose deciding quote is still fresh can have an older, non-deciding quote (e.g. a superseded manual pick) flip to `stale = true` in this same UPDATE, silently: no event names that quote, because the application itself did not change state. This is intentional -- an event per non-deciding quote would be noise on every job run -- but it means `stale = true` is not always evidence of a logged marking.
2. **`_reprice_scenario`'s not-offered quote flag** (`quotes/builder/service.py`). When a re-price finds no matching product for an existing quote (it left the grid), it recomputes the quote's display figures at the new inputs but sets `quote.stale = True` directly, not through the shared helper. The caller's one event (`quotes.repriced` / `scenario.autoquoted`) reports the ids it refreshed and deleted, but does not name the quote left stale this way.

Readiness still blocks on both: `send/readiness.py`'s `package_blockers` reads `quote.stale` off the row directly (`is_rate_stale`), so a quote flagged by either path still blocks sending regardless of which path (or no event) flagged it.

### One clock, shared

`CLOCK_NOW` (`.env.example`) is read by `core.clock.now()`, which both the API process and the Temporal worker process import -- there is exactly one env var, not a per-process override, so a demo that sets `CLOCK_NOW` in the repo-root `.env` gets the same frozen instant in both places (a reprice through the API and the stale-check job running in the worker agree on "now"). Setting it in only one process's environment (e.g. exporting it in a shell that starts just the API) desyncs them.
