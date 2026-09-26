# Merge P3/P4 (main) into P5/P6 and ship P5/P6 to main

## Context

P3/P4 is now on `main` (PR #33, merge commit 10c378b). It contains:
- CQ-017 pricing panel
- CQ-018 quote builder and reprice
- CQ-019 send tab
- CQ-020 letter PDF and SendQuotePackage workflow

`phase-p5-p6` (head ac02069) holds all of P5/P6. It was branched from phase-p3-p4 at ecbb663, so the two sides have diverged:
- main has 65 commits that phase-p5-p6 lacks
- phase-p5-p6 has 85 commits that main lacks

Goal:
1. Bring main into phase-p5-p6.
2. Reconcile the places where the lanes now overlap or disagree, including the "pending P3" items from H2.
3. Re-verify.
4. Open a phase-p5-p6 → main PR for the human.

The P5/P6 phase-verification work (branch `p56-phase-verification`, local `p56-verify-2` at 02f829c) finished before this merge:
- two full Playwright runs were green (68/68)
- lint and test were green

It must be re-run after the merge. Its finding that "P3 was never built" came from looking only at phase-p5-p6, and is out of date: P3 is on main.

## Research findings: the merge (git merge-tree on origin/phase-p5-p6 × origin/main)

### Textual conflicts and how to resolve them

1. **`backend/app/core/storage.py`** (add/add). Keep the P5/P6 module and add `object_exists(key, *, bucket=None, client=None)`. Update main's CQ-020 callers:
   - `quotes/delivery/service.py:287` and `delivery/steps.py:177,188,230`: catch `ObjectNotFoundError` instead of checking for `None`, and use `.body`.
   - `delivery/tests/test_send.py:93`: use `storage.get_client()` and `get_settings().s3_bucket`.
2. **`pricing/enrichment/router.py`**: apply main's `lock_application`, then the service call (revert now takes `user.id`), then P5/P6's `record_field_event`.
3. **`pricing/scenarios/ob_request.py`**: keep all three public constants: `DEFAULT_INVESTMENT_PPP_YEARS` from main, and `DEFAULT_DOWN_PAYMENT_PRIMARY` / `DEFAULT_DOWN_PAYMENT_INVESTMENT` from P5/P6. Point main's `pricing/panel/service.py` private copies at the public constants.
4. **`workflows/worker.py`**:
   - Take the union of ACTIVITIES and WORKFLOWS: main's `SEND_ACTIVITIES` and `SendQuotePackageWorkflow`, plus P5/P6's `load_application_source`, `resolve_clock_now`, `mark_stale_activity` and `StaleQuoteCheckWorkflow`.
   - Keep P5/P6's `run_worker` and `register_schedules`.
5. **`workflows/tests/conftest.py`**: the two sides fixed the same flake differently. Keep P5/P6's per-test `db_lock` design; five test modules depend on it. Drop main's `ActivitySessionGate` and delete or port `test_activity_session_gate.py`.
6. **`apps/lo-console/src/lib/api-client.ts`**: take either side; the change is identical.
7. **`e2e/helpers/db.ts`**: keep one copy of the `rl:*` EVAL, plus P5/P6's `execSql`, `borrowerAccountIdByEmail` and `flushSupportRateLimit`.
8. **`e2e/helpers/mailpit.ts`**: take the union.

**Generated files:** `openapi.json` and `schema.d.ts` are regenerated with `make api-client`. For `graphify-out/*`, take theirs, then run `graphify update .`.

### Merges cleanly but still broken

- `core/config.py` and `.env.example` both end up with `portal_base_url` / `PORTAL_BASE_URL` defined twice. Drop one of each.
- The route-group move carried main's edits into `app/(staff)/applications/[id]/{pricing,send}/page.tsx`. Their relative imports `../../../../features/…` now resolve to the wrong directory, which breaks the build. Switch them to `@/features/…`.
- **Two alembic heads**: `d4a1c0f2e920` (main) and `a7c3e9d1b2f4` (P5/P6), both branched from `e419a34bcdbd`. Add an `alembic merge` revision and leave the existing migrations alone.
- **Sam Reed shared state**: main's `send-tab-draft.spec.ts` and P5/P6's `workspace.spec.ts`, which withdraws and then restores him, race each other under `fullyParallel`.

### Cross-lane mismatches (the H2 "pending P3" items, now actionable)

- **Locks.** Main adds a second lock module, `applications/locks.py`, which takes FOR UPDATE and returns the Application. It is used in enrichment, scenarios, builder, send and delivery; `delivery/steps.py:256` also takes an inline FOR UPDATE.
  - Main's quote writers (reprice, `update_scenario`, override stale marking) take the application lock first and quotes second. CQ-030's `mark_stale` and CQ-033's `lock_application_quotes` take quotes first and the application second, so the two can deadlock.
  - FOR UPDATE also clashes with the KEY SHARE locks taken by activity inserts.
- **Stale marking.** CQ-017 (`enrichment/service.py::_mark_application_quotes_stale`) and CQ-018 (`builder/service.py:508`) mark quotes stale with their own code instead of CQ-030's `mark_application_quotes_stale`.
- **Reprice** (`builder/service.py:762 reprice_application`) updates Par/Buydown in place (ids stable), sets `stale=False` and a fresh `priced_at`. It never calls `clear_stale`, so a Stale application stays Stale and CQ-030 AC5 (Grace Kim) fails. `autoquote_replacing` (`:733`) has the same gap.
- **Clock (E2).** Main stamps these with `datetime.now(UTC)` instead of `core.clock.now()`:
  - `priced_at`: `scenarios/service.py:291`, `builder/service.py:648,781`
  - `sent_at`: `delivery/steps.py:134`
  - `expires_at`: `portal/reports/versions.py:64-65`
  - `send/service.py:407`, `readiness.py:96`
  - event timestamps
- **Two 21-day rules.** `send/readiness.py` has `RATE_STALE_DAYS = 21`, which duplicates the `stale_quote_days` setting.
- **Outbox PDF (CQ-029 AC2).** CQ-020 sets `attachment_keys=[version.letter_key]` in the default bucket, which works with the outbox `astream_object` stream. It is ready to verify end to end.
- **Routers and nav.** The new routers merged cleanly into `registry.py`. Main adds no new top-level routes (Pricing and Send are workspace tabs), so the nav needs no change.

## Decisions

| # | Decision |
|---|---|
| M1 | Merge on a unit branch `p56-merge-main`, cut from phase-p5-p6, with a PR into phase-p5-p6. Nothing merges straight onto phase-p5-p6. |
| M2 | Alembic: add a merge revision joining `d4a1c0f2e920` and `a7c3e9d1b2f4`, with no edits to existing migrations. Check that `make demo-reset` works and that downgrade/upgrade round-trips. |
| M3 | One lock module. `applications/locking.py` becomes the only one: `lock_application` returns the Application via `populate_existing` and takes `FOR NO KEY UPDATE`. `locks.py` is deleted and its callers re-pointed. `lock_application_quotes` switches to FOR NO KEY UPDATE. The documented order is **quotes → versions → applications**. Every quote-mutating writer takes the quotes lock before the application lock. |
| M4 | One stale path. CQ-017 and CQ-018 call `quotes.stale.service.mark_application_quotes_stale`, and the calling site writes the activity event. `reprice_application` and `autoquote_replacing` call `clear_stale(db, app_id, fresh_quote_ids=…)`, which moves Stale → Priced. `send/readiness.py` reads `stale_quote_days` from settings. |
| M5 | One clock. Every `priced_at`, `sent_at`, `expires_at` and readiness timestamp on the main side uses `core.clock.now()`. Activity-event `at` values may keep the DB default. |
| M6 | Close the stale verification branch: resume its worker only to commit and push its doc WIP and kill the slot-28 processes. Its 5c/5d content is rewritten in U4 after the merge. |

## Work units

Run them in order: each unit builds on the previous unit's merged result. Opus is used for complex units and Sonnet for simple ones. Each unit gets:
- the shared worker guide
- the context cap: 350K, 450K only to finish an atomic step, handoff at about 330K
- the verbatim 5-step block
- a fresh-reviewer stage-6 review before merge

| # | Unit | Model | Slot | Branch → PR base | Scope |
|---|---|---|---|---|---|
| U0 | Close verification WIP | Sonnet (resume existing worker) | 28 | `p56-phase-verification` (push only) | Commit and push the doc WIP. Kill the slot-28 API, worker and dev servers by PID. No PR. |
| U1 | Merge main into P5/P6 | **Opus** | 29 | `p56-merge-main` → `phase-p5-p6` | Resolve the 8 conflicts as described above. Fix the duplicate `portal_base_url`. Fix the `(staff)` pricing/send imports. Add the alembic merge revision. Adapt CQ-020 to the P5/P6 storage API. Drop `ActivitySessionGate`. Regenerate the api-client. Make `make lint`, `make test`, `make demo-reset` and the full Playwright suite (both apps and cross-app) green. Log each resolution in `docs/backlog/phase-p5-p6-main-merge.md`. |
| U2 | Lock unification (M3) | **Opus** | 30 | `p56-lock-unify` → `phase-p5-p6` | Merge `locks.py` into `locking.py` and re-point every caller. Make quote-mutating writers take the quotes lock first (reprice, `update_scenario`, override stale marking, autoquote, delivery `record`). Use FOR NO KEY UPDATE in `lock_application_quotes` and `delivery/steps.py:256`. Order `mark_stale` step 1 by id. Add two-connection tests: reprice vs `mark_stale`, send vs hard-pull accept, and no deadlock with activity inserts. |
| U3 | Stale + clock + reprice (M4, M5) | **Opus** | 31 | `p56-stale-clock` → `phase-p5-p6` | Route CQ-017 and CQ-018 stale marking through `mark_application_quotes_stale`. Add `clear_stale` in reprice and autoquote. Make readiness use the setting. Replace `datetime.now` with `clock.now()` in the listed places. Write tests for: CQ-030 AC5 (Grace Kim Stale → reprice → Priced), AC3 with `CLOCK_NOW` (send then 22 days), stale marking after overrides, and readiness under `CLOCK_NOW`. Update CQ-030 and CQ-017 post-dev.md. |
| U4 | Post-merge phase verification | Sonnet | 28 | `p56-phase-verification` (merge in phase-p5-p6) → `phase-p5-p6` | Fix the Sam Reed spec race. Add a cross-app spec for CQ-029 AC2: send Marcus's quote, then open the outbox email and download the PDF. Run the full Playwright suite twice in a row, green. Finish `phase-p5-p6-verification.md` with results, a 5c section showing each former "pending P3" item now resolved with evidence, and the 5d follow-up backlog. Make lint and test green. Open the PR. |
| U5 | Ship | me | 24 | `phase-p5-p6` → `main` | Final integration run on slot 24: lint, test, demo-reset, full e2e. Open the PR to main with a summary. The human merges it. Update Kaneo comments for CQ-017, 018, 020, 025–034, and update memory. |

U2 and U3 both edit `builder/service.py`, so they run one after the other (U2 then U3), not in parallel.

## Orchestration (each unit)

1. Launch the worker. Use `isolation: "worktree"`, and make its first command `git switch -c <branch> origin/phase-p5-p6` (these git commands are now in the allow-list).
2. When the PR is up, run a fresh-subagent review: Opus for U1, U2 and U3, Sonnet for U4.
3. Send findings to a fresh fix worker in one batch.
4. Merge into phase-p5-p6 myself. Regenerate generated files. Check `alembic heads` = 1. Run lint and test on slot 24. Push.
5. After U1 merges, tell the other session (orchestrate-p3-p4-integration) that its merged code was changed on phase-p5-p6. That covers the locks, stale marking, clock and storage API.

## Verification

- Per unit: the worker's evidence plus the reviewer's verdict. After each merge on phase-p5-p6: `make lint`, `make test`, `alembic heads` = 1, `make demo-reset` under 60 s.
- Milestones after U4:
  - **P3:** Marcus goes from import to a sent quote. The email carries the PDF and the report link.
  - **P4:** the report link works, options can be switched, and "move forward" shows OptionSelected in the console.
  - **P5:** dashboard counts match the seed. Resolving Aisha's flag takes her to Priced. Grace goes Stale, then a reprice takes her back to Priced.
  - **P6:** a new applicant becomes Priced; hard-pull consent works; the support form works.

  The full Playwright suite, which includes the P5 and P6 milestone specs, must be green twice in a row on the merged branch.
- **Final:** PR phase-p5-p6 → main is mergeable. CI is green if CI runs on PRs; otherwise the local results are attached to the PR body.
