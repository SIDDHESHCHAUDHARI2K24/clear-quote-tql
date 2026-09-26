# U1: merge `origin/main` (P3/P4) into `phase-p5-p6`

Unit U1 of `phase-p5-p6-main-merge-plan.md`. Branch `p56-merge-main`, cut from `origin/phase-p5-p6` (19726f2), merging `origin/main` (10c378b, PR #33). Slot 29: API 8129, LO 3129, portal 3229, queue `cq-s29`.

Out of scope, left for later units: lock unification (U2), and stale-path, reprice and clock unification (U3).

## Textual conflicts and how they were resolved

| # | File | Resolution | Why |
|---|---|---|---|
| 1 | `backend/app/core/storage.py` (add/add) | Kept the P5/P6 module whole. Added `object_exists(key, *, bucket=None, client=None)`, which uses the module's `_resolve` / `_is_missing` helpers (HEAD returns `False` when the object is missing). | P5/P6 callers (CQ-028/029/032) depend on `ObjectNotFoundError`, `StoredObject` and `astream_object`. Main's module offered only `put_object`, `get_object` (returning bytes or None) and `object_exists`. |
| 1a | `quotes/delivery/service.py` (`letter_pdf`) | `get_object` now catches `storage.ObjectNotFoundError` and raises `NotFoundError`; it returns `stored.body`. | Adapts to the P5/P6 API, which raises instead of returning `None`. |
| 1b | `quotes/delivery/steps.py` (email step) | Same pattern: `(await storage.get_object(key)).body`. `ObjectNotFoundError` becomes the existing `RuntimeError`. `object_exists` and `put_object(key, pdf, "application/pdf")` needed no change. | Same reason. |
| 1c | `quotes/delivery/tests/test_send.py` | `storage._client()` / `storage._bucket()` became `storage.get_client()` / `get_settings().s3_bucket`. | Those private helpers exist only in main's module. |
| 2 | `pricing/enrichment/router.py` | PATCH and revert both do main's `lock_application` (from `applications/locks.py`, unchanged here), then the service call (revert passes `user.id`, per main), then P5/P6's `record_field_event`. | Plan order. U2 unifies the lock modules. |
| 3 | `pricing/scenarios/ob_request.py` | Kept all three public constants: `DEFAULT_DOWN_PAYMENT_PRIMARY` / `_INVESTMENT` (P5/P6) and `DEFAULT_INVESTMENT_PPP_YEARS` (main, with its docstring). Dropped P5/P6's private `_DEFAULT_INVESTMENT_PPP_YEARS`. `pricing/panel/service.py` (main, CQ-017) now imports the public down-payment constants instead of keeping private copies. | One definition for each. |
| 4 | `workflows/worker.py` | ACTIVITIES and WORKFLOWS are the union: pipeline contract activities, `record_pipeline_resumed`, `load_application_source`, `resolve_clock_now`, `mark_stale_activity` and `*SEND_ACTIVITIES`; `ApplicationPipelineWorkflow`, `StaleQuoteCheckWorkflow` and `SendQuotePackageWorkflow`. P5/P6's `run_worker` and `register_schedules` are kept (that part did not conflict). | All three workflows share the slot's one task queue. |
| 5 | `workflows/tests/conftest.py` | Took the P5/P6 side whole (the per-test `db_lock` design). Dropped main's `ActivitySessionGate` / `_GatedActivitySession`, and deleted `workflows/tests/test_activity_session_gate.py`, which only tested the gate. | The two sides fixed the same flake differently, and five P5/P6 modules depend on `db_lock`. Every main hunk in this file belonged to the gate (header docstring, `contextlib` import, gate classes, `wait_for_status(gate=)`), so nothing else was lost. Main's CQ-020 delivery tests have their own conftest (`quotes/delivery/tests/conftest.py`) and do not use this one. |
| 6 | `apps/lo-console/src/lib/api-client.ts` | Ours: identical code; ours also keeps the CQ-029 comment. | |
| 7 | `e2e/helpers/db.ts` | Ours for both hunks: one `rl:*` EVAL (the same script; only comment and case differ). P5/P6's `execSql`, `borrowerAccountIdByEmail` and `flushSupportRateLimit` were already outside the conflict. | |
| 8 | `e2e/helpers/mailpit.ts` | Union: P5/P6's `waitForEmails` (CQ-034) and main's `MailpitEmail` + `readEmailsSince` (CQ-020). | Both are used. |
| G1 | `packages/api-client/openapi.json`, `src/schema.d.ts` | Regenerated with `make api-client` on the merged tree. | Generated. |
| G2 | `graphify-out/*` | Took theirs, then ran `graphify update .`. | Generated. |

## Merged cleanly but broken, and fixed

| File | Fix |
|---|---|
| `backend/app/core/config.py` | `portal_base_url` was defined twice (CQ-020 and CQ-028a). Kept one field, with a comment covering both uses. |
| `.env.example` | `PORTAL_BASE_URL` appeared twice (once commented out). Kept the active CQ-020 line and noted CQ-028a on it. |
| `apps/lo-console/src/app/(staff)/applications/[id]/{pricing,send}/page.tsx` | Relative `../../../../features/…` resolved to `src/app/features` after the `(staff)` route-group move. Switched to the `@/features/…` alias (`tsconfig` `@/*` → `./src/*`). |
| `alembic/versions/f8eb7b9f2acf_merge_main_p3_p4_into_p5p6.py` | New empty merge revision joining `d4a1c0f2e920` (main) and `a7c3e9d1b2f4` (P5/P6). No existing migration was edited. |
| `quotes/stale/tests/test_service.py`, `clients/tests/test_detail.py` | Main's CQ-019 changed `seed.loader.apply_send_fixture` to derive the package from `new_default_package`, dropping its `quote_ids` / `recommended_quote_id` kwargs. The P5/P6 callers were still passing them (mypy call-arg), so the kwargs were dropped. |

## Coordinator check: `/field-values` versus `/fields`

- **`/field-values` is not orphaned.** Main's CQ-017 pricing panel calls it: `apps/lo-console/src/features/pricing/api.ts:25` (PATCH `/api/v1/applications/{application_id}/field-values/{field_key}`) and `:32` (POST `…/revert`).
- **Activity events.** Both CQ-017 routes (`pricing/enrichment/router.py`, PATCH and revert) call `record_field_event` after the service call. CQ-028a's `/fields/{field_key}` (PUT/DELETE in `applications/sections/router.py`) does not call `record_field_event`. Instead it writes the same `field.edited` / `field.reverted` event types through `events.add_event` inside `applications/sections/fields.py` (lines ~447, 466, 565, 592). Both endpoints therefore write activity events of the same types, through two call sites.

## E2E merge fallout (test-only fixes in `e2e/**`)

The first full run on slot 29 had 80 passed, 3 failed and 5 not run. None of the failures was an app regression.

| Spec that failed | Cause | Fix |
|---|---|---|
| `lo-console/quote-builder.spec.ts` AC6 (main): Aisha has no quote cards | P5/P6's `aisha-occupancy-resume.spec.ts` runs first. It resumes Aisha to Priced, and its `afterAll` restored her status and flag but left the pipeline's `scenarios`/`quotes` in place. | Its `afterAll` now also deletes Aisha's quotes and scenarios; her seed has none. |
| `lo-console/send-tab-draft.spec.ts` AC3 (main): Kathleen's letter shows "- TBD -" | P5/P6's `property-tab.spec.ts` AC6 switches Kathleen from TBD to "100 Lake Dr" and changes her buy-box, with no restore. | Added an `afterAll` that restores her seeded property row: `address_status='tbd'`, `street_address=null`, buy-box FL / [Davenport, Orlando], `recommend_matches=true`. |
| `borrower-portal/shell.spec.ts` (P5/P6): the 375 px shell | This spec still asserted the foundation-era stub pages ("Support" heading, "Built in CQ-034/032/033"). Those pages are real now. This failure pre-dates the merge; it is not merge fallout. | The spec now asserts the real headings: "Get in touch", "Apply" and "Request not found". |

Sam Reed race (main's `send-tab-draft.spec.ts` vs P5/P6's `workspace.spec.ts`): it did not occur under `--workers=1`. I left it alone for U4, which owns that fix.

## Verification (slot 29)

| Check | Result |
|---|---|
| `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | green |
| `make test` | pytest backend 969 passed; seed 35 passed; api-client 2, ui 163, borrower-portal 156 (+1 skipped), lo-console 337 passed |
| `alembic heads` | exactly 1: `f8eb7b9f2acf` |
| alembic round trip | `downgrade e419a34bcdbd` then `upgrade head`, then `alembic check`: "No new upgrade operations detected" |
| `make demo-reset` | about 2.3 s wall time (seed reports "done in 1.2–1.7s"); under 60 s |
| Playwright, full suite (lo-console, borrower-portal, cross-app), `--workers=1 --reporter=line`, after `make demo-reset` with the API and worker restarted and both apps on 3129/3229 | **88 passed (2.5m)** |

## xfails left for U3

None. No test failed because of the lock, stale or clock gaps, so nothing was marked `xfail(reason="U3")`. U3's new tests will cover CQ-030 AC5 (reprice → `clear_stale`).
