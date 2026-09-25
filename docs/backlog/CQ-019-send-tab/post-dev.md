# CQ-019 — Post-development notes

## Summary

The Send tab (tab 7) now lets the LO pick up to 3 quotes, reorder them (drag or ▲/▼ buttons), set the recommended quote, read the server-drafted recommendation sentence, add a note, and preview exactly what the borrower gets: the portal's own `ReportPage` (with `MatchList`) and the pre-approval letter in `<iframe sandbox="">`. The backend adds the draft package (`GET`/`PUT /applications/{id}/package`, default draft on first GET), readiness, the report preview and `letter.html`. The report preview and `freeze_package_version` now call one shared function, `build_package_view_model`, so the preview and the sent report can only differ in send-time header fields (AC2). The seed's `apply_send_fixture` uses the same default-draft rule, and CQ-018 review minors n1–n3 are fixed.

## API shapes

- `GET /api/v1/applications/{id}/package` → `PackageRead` (creates the default draft on first call); `PUT` same path with `PackageUpdate {quote_ids[] (≤3, unique, this application's), recommended_quote_id (in quote_ids or null), lo_note (≤500)}` → `PackageRead`.
- `PackageRead`: `{id, application_id, quote_ids[], recommended_quote_id, recommendation_text, lo_note, recipient_email, attachments[], sent_at, updated_at}`.
- `GET /api/v1/packages/{id}/readiness` → `{ready, blockers: [{code, message, tab}]}`; codes in order: `quotes_stale`, `quote_not_offered`, `open_flag`, `no_quotes` / `no_recommended_quote`, `borrower_email_missing`.
- `GET /api/v1/packages/{id}/report` → `ReportViewModel` (CQ-021 schema).
- `GET /api/v1/packages/{id}/letter.html` → `text/html` with `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:`.
- All package routes 404 out of scope (Decision #11).

Shared builder: `app.features.quotes.send.view_model.build_package_view_model(db, package, *, recommendation_text, lo_note, as_of: date, expires_at: date | None, expired=False, superseded=False) -> ReportViewModel`.

Letter (for CQ-020): `app.features.quotes.pdf.service.render_package_letter(db, package, *, portal_url=None, letter_date=None) -> str` (wraps `build_letter_context` + pure `render_letter_html(LetterContext)`). Template variables: `letter_date, borrower_name, is_llc, lo_name, lo_title, lo_nmls, lo_phone, lo_email, lender_entity_name, lender_nmls, lender_address, lender_phone, purchase_price, loan_amount, ltv_percentage, loan_term_years, loan_type, occupancy, property_type, property_address, fico_bracket, verified_assets_display, verification_checklist[{label,status}], disclaimer_core, portal_url`. With `portal_url=None` the letter says the link arrives in the quote email; CQ-020 passes the real `/report/{token}` URL. WeasyPrint renders each persona letter to 1 page (checked with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`).

Migration: `5bd9d8620699` (`quote_packages.recommendation_text`, off `e419a34bcdbd`); `alembic heads` = 1.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Routes `/api/...` | `/api/v1/...` | Every feature router is mounted at `/api/v1` (plan Decision 1). |
| Blocker: open flag with severity `error` | `FlagSeverity.BLOCKING` | There is no `error` severity (plan Decision 10). |
| Stale = `quote.stale` | `quote.stale` OR `priced_at` > 21 days | Catalog §12 `is_rate_stale`; the seed now backdates a sent package's quotes' `priced_at` to its send time so Grace Kim is blocked (plan Decision 9). |
| Playwright `e2e/send-tab-draft.spec.ts` | `e2e/lo-console/send-tab-draft.spec.ts` | The Playwright config's projects are per app folder. |
| Recommended radio (Send tab only) | Also sets `applications.recommended_quote_id` | One recommendation per application, as CQ-018 built it (plan Decision 8). |
| — | Package capped at 3 quotes | Catalog §10 "Compares up to 3 options" (plan Decision 7). |
| Report prepay label | Investment scenario with no PPP set shows the 5-year default it was priced at | It said "No prepayment penalty" before (plan Decision 15). |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `test_default_package_draft`, `test_default_draft_puts_the_recommended_quote_first`; live: `evidence/api-checks.json` (Marcus: first-group Par first, 3 quotes, "20% down · Par pricing at 7.625%, 5-year prepay. …"); `evidence/ac1-marcus-send-tab.png`; Playwright `AC1 + AC7`. |
| AC2 | Met | `test_report_view_model_same_for_lo_and_portal[marcus_hale, kathleen_mcreynolds, priya_nair]` (freezes a draft, compares the portal JSON with the LO endpoint's, allowing only `prepared_at`, `expires_at`, `expired`, `superseded`). Live on slot 9: `evidence/ac2-live-parity.json` → `identical_except_send_time_fields: true`, no differences at all on the same day. |
| AC3 | Met | `test_letter_tbd_variant` (Kathleen: "- TBD -", par loan amount only, no rate, "720–739", "Verified Assets $80K+", assigned LO name/title/NMLS/phone/email, checklist from `documents`); live `evidence/letter-kathleen.html`, `evidence/ac3-kathleen-letter.png`. |
| AC4 | Met | `test_letter_llc_and_address_variants` (Sam Reed → "Asheville Holdings LLC"; Marcus → "4412 W Gray St, Tampa, FL 336xx"); `evidence/letter-sam-reed.html`, `evidence/letter-marcus.html`, `evidence/ac4-sam-reed-letter.png`. |
| AC5 | Met | `test_readiness_blockers[grace_kim]` → "Quotes are out of date" → `pricing`; `[aisha_coleman]` → "Open flag: Occupancy type — required for pricing"; `SendTab.test.tsx` (button disabled, tooltip = first blocker, link to Pricing); Playwright AC5; `evidence/ac5-grace-blocked.png`, `evidence/ac5-aisha-blocked.png`. |
| AC6 | Met | Playwright `e2e/lo-console/send-tab-draft.spec.ts` AC6 (remove a quote, change the radio, edit the note, reload: all persisted, note visible in the report preview); `test_put_package_persists_and_redrafts_recommendation`; `evidence/ac6-sam-after-reload.png`. |
| AC7 | Met | `npx react-doctor -y --blocking error` exit 0, no findings in `features/send`; DOM assertions: `SendTab.test.tsx` (`sandbox=""`, no `allow-scripts`) and Playwright (`iframe.sandbox.contains("allow-scripts") === false`); `evidence/ac7-marcus-letter.png`. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `make test` (`uv run pytest backend`, `uv run pytest seed`) | 521 passed; 31 passed (after review fixes) |
| Frontend tests | `make test` (`pnpm -r run test`) | api-client 2, ui 141, lo-console 138, borrower-portal 84 passed |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | Clean |
| react-doctor | `cd apps/lo-console && npx react-doctor -y --blocking error` | Exit 0; the 3 warnings it first raised in `features/send` fixed; remaining warnings are in other features |
| E2E | `pnpm exec playwright test e2e/lo-console e2e/borrower-portal --workers=1` (slot 9, after `make demo-reset`) | 48 passed (rerun after review fixes: 48 passed) |
| Migrations | `uv run alembic heads` | `5bd9d8620699 (head)` |

Note: a first `make test` hung in `test_resume_signal` because this slot's `make worker` was running on the same task queue; with the worker stopped it passed.

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | Recommendation text (rate, down payment) went stale after a reprice or scenario edit, because quote ids survive both; the sent report would carry it. | Fixed: the text is re-drafted from the recommended quote's current values on every package read, report preview and freeze (`view_model.current_recommendation_text`). Test `test_recommendation_text_follows_a_reprice`. |
| Major | Opening the Send tab created a draft that made its quotes undeletable (409) and stopped reprice cleanup. | Fixed: `builder/service._quote_in_package` now only counts *sent* packages; deleting a quote drops it from unsent drafts (`send/service.drop_quote_from_drafts`). Tests `test_draft_quote_can_be_deleted_and_leaves_the_draft`, `test_sent_package_quote_still_cannot_be_deleted`; CQ-018's `test_delete_quote_in_package_is_409` now uses a sent package. |
| Medium | The `quote_not_offered` blocker says "delete or re-pick", but deleting a drafted quote returned 409. | Fixed by the previous change (delete now works on a drafted quote). |
| Medium | The draft's recommendation and `applications.recommended_quote_id` could disagree (default draft, seed, Builder star). | Fixed: the default draft sets the application's recommendation when it has none; the Builder star updates the unsent draft (`sync_draft_recommendation`, putting the quote first, max 3). Test `test_default_draft_and_builder_star_share_one_recommendation`. |

## How to test manually

1. `source scripts/worktree-env.sh 9`, `make demo-reset`, start the API (:8109), LO console (:3109).
2. Sign in as `jordan.lee@clearquote-demo.test`, open Marcus Hale → Send: 3 quotes, the first-group Par recommended, the recommendation sentence, report preview. Switch to Pre-approval letter.
3. Open Grace Kim → Send: "Quotes are out of date" with a Pricing link; Send disabled.
4. On Sam Reed, uncheck a quote, pick another radio, type a note and click away; reload: all kept.

## Follow-ups

- The report preview for a TBD persona takes ~6 s: CQ-023's matches call the mock providers (simulated latency) per listing on every preview load. Cache matches per application/recommended quote, or skip the latency in previews.
- `backend/scripts/freeze_version.py` (used by `e2e/global-setup.ts`) creates its own package for Kathleen with every quote id; the Send tab then shows that newest package (more than 3 quotes possible). It should call `new_default_package` instead.
- WeasyPrint needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` on macOS to find pango (CQ-020).
- `builder/service.py` now calls into `send/service.py` (function-level imports to avoid an import cycle) for the draft sync on star/delete.
- New (found while fixing M6): `new_default_package` (via `_apply_default_selection` -> `recommendation_text_for`) calls `strategy_type(application)` uncaught. The *first* package GET for an investment application with no strategy set yet (no draft exists) still 422s -- only the readiness path (an *existing* package, M6's actual report) is fixed here. Low priority: a fresh application reaches Send before Property in the normal flow, so this needs the LO to open Send very early or clear the strategy after a draft already exists.

## Post-merge review round (minors)

PR #13 merged CQ-019 into `phase-p3-p4`; this branch (`cq-019-review-minors`) addresses the review's minor findings (M3 -- can a sent package be edited -- is explicitly deferred to CQ-020, per the task brief).

| # | Finding | Resolution |
| --- | --- | --- |
| M1 | `useSendTab.ts`: parallel whole-draft `PUT`s (e.g. a note-blur save racing a checkbox save) could each build a full draft from a stale snapshot and undo each other. | Saves are now serialized through a promise queue (`saveQueue`): each `update()` call computes only the fields it actually changed (`draft.ts::editedPackageFields`) against the current on-screen state, then a queued task builds the PUT body from the *last server-confirmed* package (`latestConfirmed` ref) plus that edit, so a later save always carries forward an earlier one's result instead of overwriting it. Test: `SendTab.test.tsx` "M1: a note-blur save and a checkbox save in quick succession end with the server state containing both" (gates the first `PUT`, fires both edits before releasing it, asserts the second `PUT` doesn't fire until the first lands and the mocked server ends up with both fields). |
| M2 | `package_read`'s recommendation-text refresh (`_refresh_recommendation_text`) wrote the fresh text via `db.commit()` on a plain `GET`, without `lock_application` -- a GET racing a PUT could commit a stale text *after* the PUT's fresher one. | **Decision: stop persisting on GET** (the simpler correct option). `_live_recommendation_text` now computes the same fresh text for the response only and never touches the row; the next real write (`update_package`, under the lock) is what actually refreshes the stored column. `GET /packages/{id}/report` already worked this way (`build_package_view_model` redrafts on every read without persisting) -- `package_read` now matches it. Test: `test_get_package_does_not_persist_recommendation_text` (reprices the recommended quote, confirms the GET response is fresh but the stored `recommendation_text` column is untouched). |
| M4 | `_delete_quote_row` unconditionally cleared `applications.recommended_quote_id` when the deleted quote was the app's recommendation, while `drop_quote_from_drafts` moved the *draft's* recommendation to the quote left in its place (and did so even when the draft's recommendation was already `None` -- auto-assigning one the LO had deliberately cleared). Also, `new_default_package` sets the application's recommendation from a bare `GET` with no timeline event. | `drop_quote_from_drafts` only reassigns when the deleted quote *was* the draft's own recommendation (never when it was already `None`), and returns `(application_id, new_recommended_quote_id)` when it changed one; `_delete_quote_row` now sets `applications.recommended_quote_id` to that same value (or clears it) instead of deciding independently, so the two never disagree. `new_default_package`'s auto-recommendation now logs `quote.recommended` with `actor="system"`, `source: "default_draft"`, matching the LO-initiated events (`update_package`'s `source: "send_tab"`, the Builder star's `recommend_quote`). Tests: `test_delete_recommended_quote_keeps_app_and_draft_recommendation_in_step`, `test_delete_unrelated_quote_does_not_auto_assign_a_cleared_recommendation`, `test_default_draft_logs_a_system_recommendation_event`. |
| M5 | `get_or_create_package` returned an unsent draft as-is even when it was created with `quote_ids=[]` before any quote existed (Send tab opened before pricing) -- it never got a default once quotes existed. | **Decision:** `get_or_create_package` now re-applies `default_package_selection` (via the shared `_apply_default_selection`, factored out of `new_default_package`) to an existing unsent draft whose `quote_ids` is still empty, under the same application lock as creating a brand-new draft. Test: `test_get_or_create_package_reapplies_default_to_an_empty_unsent_draft` (seeds a persona, inserts an empty draft row directly, confirms the next GET fills it and doesn't create a second package row). Fixed along the way: the new `_apply_default_selection` had to set `quote_ids=[]` at construction time in `new_default_package`, not after -- a query inside it (`default_package_selection`) autoflushes the pending INSERT, and `quote_ids` is `NOT NULL`. |
| M6 | An investment application with no LTR/STR strategy raised `ValidationAppError` inside `package_blockers` (via `load_package_context` -> `strategy_type`), 422ing `GET /packages/{id}/readiness` and leaving the Send tab stuck on "Checking readiness…". | `package_blockers` now catches that specific error and returns a `strategy_missing` blocker ("Pick a rental strategy (LTR or STR)") pointing at the Property tab, instead of letting it propagate. Test: `test_readiness_blocks_instead_of_500_when_investment_strategy_is_missing` (creates the draft while the strategy is still set, then clears it and checks readiness comes back `200` with just that blocker -- see the follow-up above for the *first-GET* variant, which is a different, out-of-scope gap). |
| M7 | `build_letter_context` did `int(fico_row)` on `FieldValue.value` (arbitrary JSONB) -- a non-numeric override 500'd the whole letter. | New `_parse_fico` parses defensively (`int`/`float`/numeric `str`, else `None`) and the letter renders with no FICO bracket instead of failing. Tests: `test_parse_fico_is_defensive_about_malformed_jsonb` (unit), `test_letter_omits_fico_bracket_for_malformed_field_value` (through the route). |
| M8 | No dedicated test for HTML-escaping an LLC name or for the letter route's CSP header (both already worked -- Jinja2 autoescape and the router's fixed header -- just untested directly). | Added `test_letter_escapes_llc_name` (`<script>x</script> LLC` renders escaped, no raw `<script>` tag in the response) and `test_letter_sends_csp_header` (asserts the exact `LETTER_CSP` header value). |
| M9 | The letter's verification checklist (catalog §10: "documents received") listed every requested document too, e.g. "Bank statements — requested". | `build_letter_context` now skips any document with `received_at is None`; the checklist lists received documents only. Updated `test_letter_tbd_variant`'s fixture-derived expectation and added `test_letter_checklist_lists_received_documents_only`. |
| M10 | `e2e/lo-console/send-tab-draft.spec.ts`'s AC6 test edits Sam Reed's real draft (removes a quote, changes the recommendation, sets a note) with no cleanup, so a rerun needed `make demo-reset` first. | Added a `test.afterAll` that PUTs Sam Reed's original package body back (captured via a `page.evaluate` fetch at the start of the AC6 test, restored via a fresh browser context + `staffLogin` in `afterAll`, the same pattern `workspace.spec.ts` uses for direct API calls). Verified live on slot 9: ran the spec twice back-to-back with no `demo-reset` between runs -- both green. |
| Nit | `send/view_model.py` module docstring listed `rates_as_of` among the header fields AC2 allows to differ between the preview and the sent report; it's actually compared for equality like every other field. | Removed it from the "may differ" list and noted it's compared. |
| Nit | `delete_quote`'s docstring said 409 applies to "a quote package (draft or sent)"; only a *sent* package blocks the delete (code review #2, already the actual behavior). | Docstring corrected. |
| Nit | The 5-year default investment PPP was defined three times (`ob_request._DEFAULT_INVESTMENT_PPP_YEARS`, `builder/service._DEFAULT_INVESTMENT_PPP_YEARS`, `view_model.DEFAULT_INVESTMENT_PPP_YEARS`), all `= 5`. | Single definition: `pricing/scenarios/ob_request.DEFAULT_INVESTMENT_PPP_YEARS` (made public, dropped the leading underscore); `builder/service.py` and `send/view_model.py` import it instead of keeping their own copy. |
| Nit | `quote_engine.py`: `_ASSET_FLOOR_STEP` was defined *after* `verified_assets_floor`, the only function that uses it. | Moved the constant above the function (Python doesn't need this at import time since it's only read inside the function body, but it reads backwards). |

Verification (slot 9): `make lint` clean (ruff, ruff format, mypy, eslint, tsc, prettier); `uv run pytest backend` 533 passed; `uv run pytest seed` 31 passed; `pnpm -r run test` all green (api-client 2, ui 141, lo-console 140, borrower-portal 84); `make demo-reset` then `pnpm exec playwright test e2e/lo-console/send-tab-draft.spec.ts --workers=1` 4 passed, rerun immediately after (no reset) also 4 passed, confirming M10's restore.

### Fresh-subagent review of this round, and its findings

A fresh subagent (`code-review`, medium effort) reviewed this branch's diff independently. Two of its findings were confirmed real regressions in the fixes above; the rest were refuted, deferred as genuinely out of scope, or accepted as latent/cleanup without a concrete bug behind them.

| Finding | Verdict | Resolution |
| --- | --- | --- |
| M5 as first written refilled a draft the LO had *deliberately* emptied (unticked every quote, saved `quote_ids: []`) -- `_is_untouched_empty_draft` couldn't tell that apart from a draft that's empty because it predates any priced quote. | Confirmed | New `quote_packages.lo_edited` column (migration `c8869567cd57`, off `5bd9d8620699`), set once `update_package` (the real `PUT`) has ever run. `get_or_create_package` only reapplies the default to an empty draft that's *never* been edited. A timestamp check (`created_at == updated_at`) was tried first and dropped: this codebase's `db_session` test fixture runs a whole test in one Postgres transaction, and `now()` is transaction-start time there, so the two columns come back equal regardless of real write order -- the column is the only reliable signal. Test: `test_a_deliberately_emptied_draft_is_not_refilled`. |
| `useSendTab.ts`: a queued save's *success* never cleared `saveError`, so an earlier queued save's failure stayed on screen after a later save landed (M1's own serialization made this worse than before: the old per-call `latestSave` counter used to make a stale result get ignored outright). | Confirmed | `runSave`'s success path now always clears `saveError`; since saves are strictly serial, the last one to run is always the most recent outcome. Test: "a later save's success clears an earlier save's error" (fails first, succeeds second, asserts the status line ends on "All changes saved"). |
| Reverting the whole `pkg` to `latestConfirmed` on a failed save could also wipe out another edit still queued behind it and not yet sent. | Plausible, same root cause as the one above | Dropped the revert entirely: a failed save now just surfaces the error and leaves the optimistic edit on screen (a reload resyncs if needed). Covered by the same new test (asserts the failed save's quote removal is still visible before the second save runs). |
| `useSendTab`'s refs (`latestConfirmed`, `saveQueue`) aren't scoped to `applicationId`; the hook doesn't remount on navigation (no `key` up the tree), so a save queued for one application could still be in flight when the LO switches to another and finish writing that application's data into the new one. | Plausible (defensive fix; not separately unit-tested -- `useWorkspace` is mocked with a fixed id in the test file, so simulating a live switch would need a larger test rig than this round's budget) | `applicationIdRef` captures the live value every render; `runSave` checks it before *and* after the network call and no-ops if the application has changed, and the load effect resets `saveQueue`/`pendingSaves`/`saving`/`saveError` on every `applicationId` change. |
| The save queue chain (`saveQueue.current.then(...)`) had no rejection handler; one throw inside a queued task would leave every later save permanently un-run. | Latent (nothing in the current code throws -- `savePackage` always resolves) | `runSave` is registered as both the fulfilled *and* rejected handler (`saveQueue.current.then(runSave, runSave)`), so the chain can't wedge. |
| `strategy_type` is still uncaught on the *first* package GET for an investment application with no strategy (only the readiness path, M6's actual finding, is fixed). | Confirmed pre-existing gap, correctly out of scope | Already logged as a follow-up above; M6 test restructured to create the draft before clearing the strategy so it exercises the readiness fix specifically. |
| M7's defensive FICO parsing isn't reused by pricing's own reads of the same `representative_fico` JSONB (`pricing/scenarios/service.py`, `pricing/panel/service.py`). | Correctly out of scope | Same class of bug, but outside this round's diff and outside M7's stated target (the letter). Left as a follow-up rather than touched here. |
| The new system `quote.recommended` `ActivityEvent` in `_apply_default_selection` duplicates the shape of the one in `update_package`; `builder/service.py` already has an `_event()` helper for this. | Cleanup, no bug | Not extracted in this round -- accepted as minor duplication (two call sites, different actor/source) rather than a design change beyond the assigned findings. |
| `pendingSaves` duplicates what the promise chain already tracks. | Cleanup, no bug | Kept as-is; comparing `task === saveQueue.current` would remove the counter but isn't a correctness fix. |

Re-verified after these fixes (slot 9): `uv run pytest backend` 533 passed; `make lint` clean; `pnpm --filter @cq/lo-console exec vitest run src/features/send` 30 passed; `make demo-reset` + `send-tab-draft.spec.ts --workers=1` 4 passed.
