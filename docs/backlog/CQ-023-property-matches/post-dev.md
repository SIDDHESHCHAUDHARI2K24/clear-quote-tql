# CQ-023 — Post-development notes

## Summary

Built the property-match engine: `app.features.matches.service.compute_matches_for_package`
runs up to 3 seeded listings through the exact `quote_engine` (`compute_quote`) the
borrower's own recommended quote used — same down payment %, note rate, discount points and
FICO, each listing's own price plus real mock-provider enrichment (tax rate, insurance, market
rent/STR revenue). `GET /api/v1/applications/{id}/matches` (LO auth) exposes it live;
`portal/reports/versions.py::freeze_package_version` calls the same function so matches are
frozen into the sent `ReportViewModel` snapshot forever (AC7). `ReportMatch`/`ReportMatchInput`
(CQ-021's report contract) grew the spec's new fields additively. `MatchCard`/`MatchList`
(`packages/ui/src/report/`) render "Your top 3 property matches"; `ReportMatchesSlot.tsx` now
renders them for real instead of always `null`. `provider_listings` gained `county` (tax-rate
lookups) and `str_permitted` (STR strategy fit) via a new migration chained off the P3/P4
foundation head.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Catalog names the buy-box field `buy_box_market_cities` | Used the built name `buy_box_metros` (`Property` model, CQ-007) throughout | AGENTS.md/prompt: "use the built name and log a Decision" — matches an existing codebase convention (the model was already built this way before this item). |
| `find_matches(application, recommended_option) -> list[Match]` (spec.md) | One function, `compute_matches_for_package(db, *, application, recommended_quote) -> list[ReportMatchInput]` (phase-p3-p4-plan.md D4's name) | The coordinator's brief pins the concrete name CQ-019/CQ-020 will actually call; spec.md's name was descriptive, not binding syntax. Logged as plan.md Decision 6. |
| "primary → owner-occupant listings" strategy fit | No new `owner_occupant` column; primary uses the full price-band+geography candidate set, same as LTR minus the ranking metric | data-field-catalog §4/§11 has no listing attribute for this, and the seeded mock inventory (`provider_listings`) is generic single-family homes with no owner-occupant/investment split to filter on. Only `str_permitted` (explicitly named by the catalog's "STR-zoned community" tagline example and spec.md AC5) is a real new column. Logged as plan.md Decision 2. |
| — (not specified) | Primary matches ranked by ascending `total_monthly_payment` (cheapest first) | Spec.md pins LTR-by-cashflow and STR-by-DSCR but gives no primary ranking rule. Logged as plan.md Decision 8. |
| — (not specified) | `applications.recommended_quote_id` is CQ-018's column and isn't set by anything yet (CQ-018 hasn't merged into `phase-p3-p4`) | `_resolve_recommended_quote` falls back to the application's earliest-created scenario's `"Par"` quote (mirrors `seed/loader.py::apply_send_fixture`'s own `quote_ids[0]` convention) when the column is `NULL`. Logged as plan.md Decision 7. Once CQ-018 merges and starts setting the column, this fallback simply stops being hit for newly-recommended applications. |
| — (not specified) | A candidate listing whose provider enrichment call raises (`IntegrationError` — forced-fail toggle, or a missing seeded zip/state row) is silently dropped from the candidate set instead of failing the whole request | Matches is a "nice to have" report surface, not a blocking pipeline stage; one bad listing shouldn't 500 the whole matches list. Logged as plan.md Decision 9. |
| — (not specified) | `provider_listings.county` added, backfilled on all 10 original seed rows from the matching `tax_rates.yaml` `(state, county)` row | `MockTaxClient.get_tax_rate(state, county)` needs a county per listing; the model had none. Logged as plan.md Decision 3. |
| — (not specified) | Rent/STR-revenue calls use `beds=1` for every listing (not the listing's own bed count) | `seed/providers/rents.yaml`/`str_revenue.yaml` are only ever seeded at `beds=1` (the existing convention: keyed on `Property.number_of_units`, always 1 for single-family, not a literal bedroom count — see `seed/tests/test_personas_match_engine.py`'s own comment). Logged as plan.md Decision 5. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Met | `backend/app/features/matches/tests/test_service.py::test_matches_kathleen` — Kathleen McReynolds's real seeded numbers (FICO 720, tax 0.0089, market rent $2,250, $300,000 approved, FL/[Davenport, Orlando]) produce exactly 3 matches, each price in `[$210,000, $300,000]`, sorted by `monthly_cashflow` descending. Live API check (Casey Nguyen, manager, GET `/api/v1/applications/{kathleen}/matches`): 3 matches, $220,000/$255,000/$280,000, cashflow $1,031.11 > $837.20 > $698.69. Screenshots: `evidence/report-matches-375px.png`, `evidence/report-matches-1120px.png` (live `/report/{token}` page via `freeze_version.py`). |
| AC2 | Met | `test_service.py::test_match_numbers_match_engine` — recomputes each returned match's `total_monthly_payment`/`cash_to_close` directly via `quote_engine.compute_quote` with the recommended option's own terms and the listing's real seeded tax/insurance/rent data; asserts equality against the service's own output. |
| AC3 | Met | `backend/app/features/matches/tests/test_router.py::test_no_matches_with_address` (a Priya-Nair-shaped, specific-address application gets `{"matches": []}`, not an error) + `test_service.py::test_no_matches_for_specific_address`. Live API check: GET Priya Nair's real application → `{"matches": []}`. |
| AC4 | Met | `test_service.py::test_matches_toggle_off` (`recommend_matches=False` → `[]`). Live check: toggled Kathleen's `properties.recommend_matches` to `false` in the dev DB, GET returned `{"matches": []}`, restored to `true` after. |
| AC5 | Met | `test_service.py::test_match_ranking_by_strategy` (a synthetic STR/TBD Tampa application: 3 `str_permitted` listings returned, sorted by `dscr_ratio` descending — via `rank_key` on the STR path; a 4th in-band-but-not-`str_permitted` Tampa listing never appears) + `test_match_ranking_primary_has_no_rental_fields` (primary matches carry `rent_estimate`/`rent_label`/`monthly_cashflow`/`cap_rate_pct`/`year1_tax_savings` all `None`, but still carry `total_monthly_payment`/`cash_to_close`). `packages/ui/src/report/MatchCard.test.tsx::"omits rent, cashflow, cap rate and tax savings for a primary match (AC5)"`. |
| AC6 | Met | `backend/app/features/pricing/engine/tests/test_match_price_band.py::test_price_band_boundaries` (pure: `match_floor_price`/`match_ceiling_price` — 69%/70%/100%/101% boundary math) + `test_service.py::test_matches_kathleen`'s own boundary assertion (the seeded 69%/101% Davenport listings, `$207,000`/`$303,000`, never appear in Kathleen's 3 matches, confirmed against real DB rows). |
| AC7 | Met | `backend/app/features/portal/reports/tests/test_versions.py::test_matches_frozen_in_version` — freezes a version, captures its snapshot's `matches`, deletes every `provider_listings` row, re-reads the same version from the DB: `matches` unchanged (it's a plain JSONB copy, never recomputed on read). |
| AC8 | Met | `packages/ui/src/report/MatchList.test.tsx` (`grid-cols-1`/`lg:grid-cols-3` class assertions) + `e2e/borrower-portal/report-matches.spec.ts` (375px: cards stack vertically, no horizontal scroll; 1120px: all 3 cards share one row) — both passed live against the real dev server. `react-doctor -y --blocking error`: lo-console 81/100 (4 pre-existing warnings, 0 new), borrower-portal 81/100 (3 pre-existing warnings, 0 new). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend + seed | `uv run pytest backend seed -q` | 450 passed |
| Matches feature only | `uv run pytest backend/app/features/matches -q` | 12 passed |
| Engine (band boundaries) | `uv run pytest backend/app/features/pricing/engine/tests/test_match_price_band.py -q` | 2 passed |
| Portal reports (AC7 + regressions) | `uv run pytest backend/app/features/portal/reports -q` | 10 passed |
| Ruff | `uv run ruff check backend seed` | All checks passed |
| Ruff format | `uv run ruff format --check backend seed` | 320 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 303 source files |
| `alembic heads` | `uv run alembic heads` | `e419a34bcdbd (head)` — single head |
| `make demo-reset` | `time make demo-reset` | ~1.5s, well under the 60s budget |
| Frontend (whole monorepo) | `pnpm -r run test` | 4/4 workspaces — ui 141, lo-console 39, borrower-portal 68 (248 total) |
| ESLint | `pnpm -r run lint` | 0 errors |
| TypeScript | `pnpm -r run typecheck` | 0 errors |
| TypeScript (root, covers e2e/) | `pnpm exec tsc --noEmit -p tsconfig.json` | 0 errors |
| Prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| `make api-client` | `make api-client` | Regenerated; `MatchListResponse`/`GET .../matches` and the extended `ReportMatch` present |
| react-doctor (lo-console) | `npx react-doctor -y --blocking error` | 81/100; 4 pre-existing warnings (`page.tsx` ×3, `WorkspaceProvider.tsx` ×1 — CQ-016, not touched here), 0 new |
| react-doctor (borrower-portal) | `npx react-doctor -y --blocking error` | 81/100; 3 pre-existing warnings (`page.tsx` ×2, `ReportView.tsx` ×1 — CQ-022, not touched here), 0 new |
| Playwright — `report-matches.spec.ts` | `pnpm exec playwright test e2e/borrower-portal/report-matches.spec.ts --project=borrower-portal` | 2/2 passed |
| Playwright — borrower-portal (full) | `pnpm exec playwright test e2e/borrower-portal --project=borrower-portal --workers=1` | 14/14 passed |
| Playwright — lo-console (report-gallery + smoke + staff-login + workspace) | `pnpm exec playwright test e2e/lo-console --project=lo-console --workers=1` | 10/11 passed — the 1 failure (`workspace.spec.ts::AC7 pipeline banner`) needs a running Temporal worker (`make worker`), out of this item's E2E recipe and this item's owned files (CQ-016); confirmed unrelated by inspecting the failure (waits on a live pipeline run, nothing to do with matches/report pages). |
| Live API (Casey Nguyen, manager) | `curl .../applications/{kathleen}/matches` | 3 matches, band-correct, cashflow-sorted |
| Live API (Jordan Lee, LO) | `curl .../applications/{priya}/matches` | `{"matches": []}` |
| Live toggle | `UPDATE properties SET recommend_matches=false ...` then GET | `{"matches": []}`; restored after |

## Review findings (stage 6)

Ran the `code-review` skill (fresh, isolated fork) over the full diff. See the coordinator's
own re-review before merge per AGENTS.md stage 6 (fresh subagent that did not write the code).

_(Findings recorded below once the fork's report lands; none blocking landed by the time this
file was written — see handoff.md if the fork is still running when this session ends.)_

## How to test manually

1. `source scripts/worktree-env.sh 6` (or reuse this worktree's `.env`, already slot 6).
   `uv sync && pnpm install`, `uv run alembic upgrade head`, `make demo-reset`.
2. Backend: `uv run uvicorn app.main:app --port 8106` in the background.
3. Portal: `pnpm --filter @cq/borrower-portal exec next dev -p 3206` in the background.
4. Freeze a sent version for Kathleen: `uv run python backend/scripts/freeze_version.py
   --persona kathleen_mcreynolds` — prints the report token.
5. LO API check: sign in as `casey.nguyen@clearquote-demo.test` (manager — Jordan Lee doesn't
   own Kathleen's application in the seed data, so use a manager or `morgan.reyes@clearquote-
   demo.test`), `GET /api/v1/applications/{kathleen's id}/matches`.
6. Borrower UI: sign in at `http://localhost:3206/login` as `kathleen.mcreynolds@clearquote-
   demo.test` / `$SEED_BORROWER_PASSWORD`, visit `/report/{token}` from step 4. See "Your top 3
   property matches" with 3 cards.
7. `pnpm exec playwright test e2e/borrower-portal/report-matches.spec.ts --project=borrower-portal`
   (needs `PORTAL_BASE_URL`, `SEED_BORROWER_PASSWORD`, `DATABASE_URL` set).

## Follow-ups

- CQ-018 (Quote Builder) will start setting `applications.recommended_quote_id`; once merged,
  `_resolve_recommended_quote`'s "Par of earliest scenario" fallback (Decision 7) simply stops
  being the common path for freshly-priced applications — no code change needed, just noting it.
- CQ-019's draft builder and CQ-020's send workflow both call `compute_matches_for_package(db,
  application=..., recommended_quote=...)` directly — the recommended quote they pass should be
  the one they're about to draft/send with, not necessarily `_resolve_recommended_quote`'s
  fallback (that resolver is only for the live GET endpoint's "no explicit selection yet" case).
- `MatchCard`'s `property_image_url` renders as a plain `<img>` (no Next.js `Image` — this
  package is framework-agnostic). Real `picsum.photos` seed URLs need outbound network access
  to render in a screenshot; the evidence screenshots in this repo show the placeholder gray box
  since the sandboxed test run had none, but the layout/data are unaffected.
