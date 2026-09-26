# U2 (P5/P6 → main merge): lock unification — post-development notes

Branch `p56-lock-unify` → `phase-p5-p6`. Merge plan decision **M3**, unit **U2** (`docs/backlog/phase-p5-p6-main-merge-plan.md`, the "Locks" finding). Slot 30.

## Summary

Before this change there were two lock modules. P3's `applications/locks.py` took `FOR UPDATE` and returned the Application. P5/P6's `applications/locking.py` took `FOR NO KEY UPDATE`. They also used opposite orders:
- P3's quote writers took the application lock first and the quotes second.
- CQ-030 `mark_stale` and the CQ-033 hard pull took the quotes first.

Reprice racing `mark_stale` on one application deadlocked, and the new test reproduced it on every run.

After:

- **One module**, `backend/app/features/applications/locking.py`:
  - `lock_application(db, id) -> Application` takes `FOR NO KEY UPDATE`, re-reads the row with `populate_existing`, and raises 404 when the application is missing.
  - `lock_application_quotes` takes `FOR NO KEY UPDATE OF quotes`, ordered by id. It moved here from `credit/hard_pull.py`.
  - `lock_application_packages` is new. It locks `quote_packages` `FOR UPDATE`, ordered by id.
  - `locks.py` is deleted.
- **One order**, documented in the module docstring: **quotes → packages/versions → applications**.

| Writer | Locks now |
| --- | --- |
| `reprice_application`, `autoquote_replacing`, `delete_quote` (`builder/service.py`, via `_lock_for_quote_writes`) | quotes → packages → application |
| `update_scenario` | quotes → application |
| CQ-017 override / revert (`pricing/enrichment/router.py`) | quotes → application |
| `recommend_quote` (the star edits the unsent draft) | packages → application |
| Send tab `update_package`, `get_or_create_package` slow path (`send/service.py`) | packages → application |
| Delivery `record` (`delivery/steps.py`, which UPDATEs the package at its end) | package → application (`lock_application` replaces the inline `FOR UPDATE`) |
| Delivery `freeze` | package → version (unchanged, no application lock) |
| Portal report actions (`portal/actions/service.py`) | package → version → application (`lock_application` replaces the inline `FOR UPDATE`) |
| Summary status PATCH (`applications/summary/service.py`) | application (`lock_application` replaces the inline `FOR UPDATE`) |
| CQ-030 `mark_stale` | step 1 locks every quote it may touch by id, then UPDATEs only locked rows → versions → applications (`FOR NO KEY UPDATE`) |
| CQ-033 hard-pull accept | quotes → application (import moved; now NO KEY) |
| Scenario create, manual quote (insert only) | application (import re-pointed) |

- **PR #34 review m2.** The override or revert and its `field.edited`/`field.reverted` event now commit in one transaction under the locks.
  - `override_field_value` and `revert_field_value` take `commit=False`, which only flushes.
  - `record_field_event` adds the event and makes the single commit.
  - The event contents are unchanged.

## Deviations from spec

- **Decision: package layer added.** The M3 order names "versions/packages". Checking `send/service.py` and `delivery/steps.py` against it found application → package orders:
  - `update_package`
  - the draft edits made by star, delete and reprice
  - `record`

  The borrower's report actions take package → version → application, so each of those paths could deadlock against them. `lock_application_packages` fixes this. Packages keep `FOR UPDATE`, the mode every other package lock already uses.
- **Decision: `mark_stale` step 1 locks a superset.**
  - Step 1 locks the quotes past the cutoff *and* every quote of a step-3 candidate application (Priced, Sent, Viewed, Inquiry, OptionSelected), in one statement ordered by id.
  - The job then takes no quote locks after versions or applications, so it cannot invert against a per-application quote writer that locks in id order.
  - The step-3 quote re-lock stays, but it only matters for an application whose status changed between step 1 and step 3.
  - Step-3 application locks are `FOR NO KEY UPDATE`.
- **Decision: the other inline application `FOR UPDATE` locks also became `lock_application`.** This covers the summary PATCH and the portal actions. The goal is one lock mode with no key-share clashes against activity inserts.
- **Decision: no id-only variant.** No P5/P6 caller needed one: autoflush runs before the re-read, and every caller's application exists. All callers use `lock_application`.
- **Out of scope (U3), untouched:**
  - stale-path unification
  - `clear_stale` in reprice
  - the clock

  Only the lock calls in those functions changed.

## Acceptance evidence (stage 7)

| Criterion | Evidence |
| --- | --- |
| One lock module; `locks.py` deleted; callers re-pointed | `git grep applications.locks` → none. `lock_application_quotes` now lives only in `locking.py`. |
| Quote writers lock quotes before the application | `test_every_builder_write_locks_the_application_row` (extended). It captures SQL for reprice, autoquote, PUT, override, revert and delete, and asserts that the `FOR NO KEY UPDATE OF quotes` lock comes before the application lock. For reprice, autoquote, star and delete it asserts the package lock comes before the application lock. |
| Reprice vs `mark_stale`: no deadlock, consistent end state | `test_lock_order.py::test_reprice_holding_its_locks_then_mark_stale_does_not_deadlock`. It fails on the old code with `DeadlockDetectedError`. `test_mark_stale_holding_its_locks_then_reprice_does_not_deadlock` covers the reverse order: fresh quotes, one stale event. |
| `mark_stale` step 1 locks by id before its UPDATE | `test_mark_stale_locks_its_quotes_by_id_before_updating`, plus `stale/tests/test_service.py`, which asserts the quote lock comes before the first `UPDATE quotes`. |
| Send (freeze/record) vs hard-pull accept: no deadlock | `test_hard_pull_holding_its_locks_then_send_does_not_deadlock` and `test_send_record_holding_its_lock_then_hard_pull_does_not_deadlock` |
| Send `record` vs an LO star (review finding 1) | `test_send_record_holding_its_locks_then_a_star_does_not_deadlock`. It deadlocked before the fix. |
| Activity insert not blocked by `lock_application` | `test_activity_insert_is_not_blocked_by_the_application_lock`. The quotes, packages and application are all held while another session inserts an event under `lock_timeout = 1s`. |
| Override + event atomic (m2) | `test_override_and_its_event_commit_together[False/True]`. A forced event failure leaves the field value, quote `stale` flags and `quotes.marked_stale` count unchanged. Both cases failed before the fix. `test_override_commits_the_override_and_both_events` covers the happy path. |
| Every existing P3 and P5/P6 test passes | `make test` green: backend 981 passed, seed 35 passed, all frontend suites passed. |

## Test log (stage 5)

- `make lint`: exit 0 (ruff, mypy with 509 files clean, eslint, tsc, prettier).
- `make test`: exit 0. Backend 981 passed. Seed 35 passed. api-client 2, ui 163, borrower-portal 156 (1 skipped), lo-console 337.
- Flake check: the lock-related suites ran 3× in a row, 186 passed each time (`applications/tests/test_lock_order.py`, `sections/tests/test_lock_hardening.py`, `test_concurrency.py`, `portal/consents/tests`, `quotes/`, `pricing/enrichment`, `portal/actions`).
- `make demo-reset` on `cq_dev_s30`: exit 0, about 2 s.
- Playwright on slot 30 (API 8130, LO 3130, portal 3230, queue `cq-s30`), full suite with `--workers=1 --reporter=line`: **88 passed**. It ran twice, before and after the review fixes; the second run followed a fresh demo-reset and an API/worker restart.
  - The first attempt skipped 78 specs because `SEED_*_PASSWORD` was not exported.
  - The screenshot churn the suite writes under `docs/backlog/*/evidence` was reverted.

## Review findings (stage 6)

`code-review` (medium) on `origin/phase-p5-p6...HEAD`:

| Severity | Finding | Resolution |
| --- | --- | --- |
| High | `record` took the application lock, then `_set_step` UPDATEd the package: application → package. The new package-first writers (star, Send PUT) would deadlock with it. | Fixed. `record` locks the package `FOR UPDATE` (with `populate_existing`) before `lock_application`. Covered by the new record-vs-star test (red before the fix). |
| Low | The `get_or_create_package` slow path re-read the draft without `populate_existing`, so a concurrent PUT's committed selection could be overwritten by the default selection. | Fixed with `_newest_package(..., fresh=True)`. Covered by `test_first_load_rereads_the_draft_under_the_lock` (red before the fix). |

## How to test manually

1. Run `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python -m pytest backend/app/features/applications/tests/test_lock_order.py -q` from the repo root.
2. To see the original deadlock, check out `origin/phase-p5-p6`'s `builder/service.py` and rerun `test_reprice_holding_its_locks_then_mark_stale_does_not_deadlock`.

## Follow-ups

- A residual edge remains in `mark_stale`: an application that *becomes* a candidate between step 1 and step 3 has its quotes locked late. A reprice holding a lower-id quote of that application while waiting on an old one the job locked in step 1 could still cycle. This needs a status change committed mid-job; accepted and documented.
- U3 keeps the lock calls as they are when it routes CQ-017/018 stale marking through `mark_application_quotes_stale` and adds `clear_stale`. `clear_stale` already follows quotes → application.
