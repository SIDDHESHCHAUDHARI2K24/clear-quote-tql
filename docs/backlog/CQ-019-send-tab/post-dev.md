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
