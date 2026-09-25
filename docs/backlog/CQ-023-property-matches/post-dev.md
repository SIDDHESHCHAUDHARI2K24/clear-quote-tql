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
| AC1 | Met | `backend/app/features/matches/tests/test_service.py::test_matches_kathleen` — Kathleen McReynolds's real seeded numbers (FICO 720, tax 0.0089, market rent $2,250, $300,000 approved, FL/[Davenport, Orlando]) produce exactly 3 matches, each price in `[$210,000, $300,000]`, sorted by `monthly_cashflow` descending. Live API check (Casey Nguyen, manager, GET `/api/v1/applications/{kathleen}/matches`): 3 matches, $220,000/$255,000/$280,000, cashflow $1,031.11 > $837.20 > $698.69. Screenshots: `evidence/report-matches-375px.png`, `evidence/report-matches-1120px.png` (live `/report/{token}` page via `freeze_version.py`). **Round 1:** `test_router.py::test_matches_happy_path_tbd_ltr` — the same shape asserted through the real `GET .../matches` route, not `compute_matches_for_package` called directly. |
| AC2 | Met | `test_service.py::test_match_numbers_match_engine` — recomputes each returned match's `total_monthly_payment`/`cash_to_close` directly via `quote_engine.compute_quote` with the recommended option's own terms and the listing's real seeded tax/insurance/rent data; asserts equality against the service's own output. **Round 1:** `test_resolver.py`'s two new tests recompute the same way for `find_current_matches`'s two resolution paths (explicit `recommended_quote_id`, and the Par-of-earliest-scenario fallback); `pricing/engine/tests/test_insurance_annual_rate_from_amount.py` covers the new `insurance_annual_rate_from_amount` engine function directly (unrounded division, `NonPositivePriceError`). |
| AC3 | Met | `backend/app/features/matches/tests/test_router.py::test_no_matches_with_address` (a Priya-Nair-shaped, specific-address application gets `{"matches": []}`, not an error) + `test_service.py::test_no_matches_for_specific_address`. Live API check: GET Priya Nair's real application → `{"matches": []}`. |
| AC4 | Met | `test_service.py::test_matches_toggle_off` (`recommend_matches=False` → `[]`). Live check: toggled Kathleen's `properties.recommend_matches` to `false` in the dev DB, GET returned `{"matches": []}`, restored to `true` after. |
| AC5 | Met | `test_service.py::test_match_ranking_by_strategy` (a synthetic STR/TBD Tampa application: 3 `str_permitted` listings returned, sorted by `dscr_ratio` descending — via `rank_key` on the STR path; a 4th in-band-but-not-`str_permitted` Tampa listing never appears) + `test_match_ranking_primary_has_no_rental_fields` (primary matches carry `rent_estimate`/`rent_label`/`monthly_cashflow`/`cap_rate_pct`/`year1_tax_savings` all `None`, but still carry `total_monthly_payment`/`cash_to_close`). `packages/ui/src/report/MatchCard.test.tsx::"omits rent, cashflow, cap rate and tax savings for a primary match (AC5)"`. |
| AC6 | Met | `backend/app/features/pricing/engine/tests/test_match_price_band.py::test_price_band_boundaries` (pure: `match_floor_price`/`match_ceiling_price` — 69%/70%/100%/101% boundary math) + `test_service.py::test_matches_kathleen`'s own boundary assertion (the seeded 69%/101% Davenport listings, `$207,000`/`$303,000`, never appear in Kathleen's 3 matches, confirmed against real DB rows). |
| AC7 | Met | `backend/app/features/portal/reports/tests/test_versions.py::test_matches_frozen_in_version` — freezes a version, captures its snapshot's `matches`, deletes every `provider_listings` row, re-reads the same version from the DB: `matches` unchanged (it's a plain JSONB copy, never recomputed on read). |
| AC8 | Met | `packages/ui/src/report/MatchList.test.tsx` (`grid-cols-1`/`lg:grid-cols-3` class assertions) + `e2e/borrower-portal/report-matches.spec.ts` (375px: cards stack vertically, no horizontal scroll; 1120px: all 3 cards share one row) — both passed live against the real dev server. `react-doctor -y --blocking error`: lo-console 81/100 (4 pre-existing warnings, 0 new), borrower-portal 81/100 (3 pre-existing warnings, 0 new). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend + seed | `uv run pytest backend seed -q` | 459 passed (round 1: was 450, +9 new tests) |
| Matches feature only | `uv run pytest backend/app/features/matches -q` | 16 passed (round 1: was 12, +4: 2 resolver + 1 router happy-path + 1 tie-break) |
| Engine (band boundaries) | `uv run pytest backend/app/features/pricing/engine/tests/test_match_price_band.py -q` | 2 passed |
| Engine (insurance rate, round 1) | `uv run pytest backend/app/features/pricing/engine/tests/test_insurance_annual_rate_from_amount.py -q` | 5 passed |
| Portal reports (AC7 + regressions) | `uv run pytest backend/app/features/portal/reports -q` | 10 passed |
| Ruff | `uv run ruff check backend seed` | All checks passed |
| Ruff format | `uv run ruff format --check backend seed` | 322 files already formatted |
| Mypy | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | Success: no issues found in 305 source files |
| `alembic heads` | `uv run alembic heads` | `e419a34bcdbd (head)` — single head |
| `make demo-reset` | `time make demo-reset` | ~1.7s, well under the 60s budget |
| Frontend (whole monorepo) | `pnpm -r run test` | 4/4 workspaces — api-client 2, ui 141, lo-console 39, borrower-portal 68 (250 total) |
| ESLint | `pnpm -r run lint` | 0 errors |
| TypeScript | `pnpm -r run typecheck` | 0 errors |
| TypeScript (root, covers e2e/) | `pnpm exec tsc --noEmit -p tsconfig.json` | 0 errors |
| Prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| `make api-client` | `make api-client` | Regenerated; `MatchListResponse`/`GET .../matches` and the extended `ReportMatch` present |
| react-doctor (lo-console) | `npx react-doctor -y --blocking error` | 81/100; 4 pre-existing warnings (`page.tsx` ×3, `WorkspaceProvider.tsx` ×1 — CQ-016, not touched here), 0 new |
| react-doctor (borrower-portal) | `npx react-doctor -y --blocking error` | 81/100; 3 pre-existing warnings (`page.tsx` ×2, `ReportView.tsx` ×1 — CQ-022, not touched here), 0 new |
| Playwright — `report-matches.spec.ts` | `pnpm exec playwright test e2e/borrower-portal/report-matches.spec.ts --project=borrower-portal` | 2/2 passed |
| Playwright — `report-matches.spec.ts` (round 1, no manual step) | `pnpm exec playwright test e2e/borrower-portal/report-matches.spec.ts --workers=1` | 2/2 passed; `global-setup.ts`'s own output shows `freeze_version.py` ran automatically ("Reusing existing quote_package_versions.id=... (unexpired, not superseded)" on the 2nd+ run) — no manual step, confirmed idempotent by running the whole suite twice in a row. |
| Playwright — borrower-portal (full) | `pnpm exec playwright test e2e/borrower-portal --project=borrower-portal --workers=1` | 14/14 passed |
| Playwright — lo-console (report-gallery + smoke + staff-login + workspace) | `pnpm exec playwright test e2e/lo-console --project=lo-console --workers=1` | 10/11 passed — the 1 failure (`workspace.spec.ts::AC7 pipeline banner`) needs a running Temporal worker (`make worker`), out of this item's E2E recipe and this item's owned files (CQ-016); confirmed unrelated by inspecting the failure (waits on a live pipeline run, nothing to do with matches/report pages). |
| Live API (Casey Nguyen, manager) | `curl .../applications/{kathleen}/matches` | 3 matches, band-correct, cashflow-sorted |
| Live API (Jordan Lee, LO) | `curl .../applications/{priya}/matches` | `{"matches": []}` |
| Live toggle | `UPDATE properties SET recommend_matches=false ...` then GET | `{"matches": []}`; restored after |

## Review findings (stage 6)

Ran the `code-review` skill (fresh, isolated fork) over the full diff. The fork's report landed
after handoff 1 and combined with a fresh stage-6 review from the coordinator into the batch
fixed in "PR review round 1" below.

## PR review round 1

Fixes for the batched findings from the fresh stage-6 review + the predecessor's `code-review`
fork, applied on top of handoff 1's code (PR #7).

| # | Severity | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | MAJOR | `_resolve_recommended_quote` (service.py ~86-124) and `find_current_matches` (~320-331) had no direct test coverage — only exercised indirectly through `compute_matches_for_package` tests that always pass an explicit `recommended_quote`. | Added `recommended_quote_id` param to `matches/tests/conftest.py::make_application`. New `backend/app/features/matches/tests/test_resolver.py`: (a) `test_find_current_matches_uses_recommended_quote_id` — sets `application.recommended_quote_id` to a non-Par, non-first ("Buydown") quote and asserts every match is priced with that quote's own rate/points, recomputed via `quote_engine.compute_quote` directly (and asserts the Par quote's terms would have produced a *different* number, so the test can't pass by accident); (b) `test_find_current_matches_falls_back_to_earliest_scenarios_par_quote` — two manually-built scenarios (several quotes each, one scenario's Buydown persisted *before* its own Par to rule out a naive "first quote row" bug) with distinct `created_at`, `recommended_quote_id` left unset, asserts the fallback picks the earliest scenario's `"Par"` quote specifically. New `test_router.py::test_matches_happy_path_tbd_ltr` — a real `GET /api/v1/applications/{id}/matches` call (not `compute_matches_for_package` called directly) for a Kathleen-McReynolds-shaped TBD LTR persona, asserts 3 in-band, LTR-labeled matches. 16 matches-feature tests now (was 12). |
| 2 | MUST-FIX | `insurance.annual_premium / listing.list_price` computed a rate directly in `service.py`, outside `quote_engine` (AGENTS.md: money math lives only in `quote_engine`). | Added `insurance_annual_rate_from_amount(purchase_price, annual_premium) -> Decimal` to `quote_engine.py`, copied **verbatim** from CQ-017 (`origin/cq-017-pricing-panel` @ `12cefaf`, same name/signature/docstring/behavior — including `NonPositivePriceError`), in its own clearly marked "Insurance rate conversion (shared with CQ-017)" block so the merge keeps one copy. `service.py` now calls it instead of dividing inline. New `pricing/engine/tests/test_insurance_annual_rate_from_amount.py`: unrounded-division, non-terminating-fraction (no truncation), zero-price and negative-price `NonPositivePriceError` cases, and a `ValueError` catchability check. |
| 3 | MINOR | Migration `e419a34bcdbd` added `provider_listings.county` as `NOT NULL` with no default — fails on a non-empty table. | Added `server_default=sa.text("''")` to the `county` column. `alembic heads` still a single head (`e419a34bcdbd`). |
| 4 | MINOR | `_candidate_listings`/the final ranking had no deterministic tie-break — a `rank_key` tie's order depended on whatever order Postgres returned rows in. | The final `candidates.sort(...)` sorts on `(sign * rank_key, matched_property_id)` — an explicit total order (id tie-break always ascending; `sign` flips only the rank_key direction) that doesn't depend on the order `_candidate_listings`' rows arrive in, so no `ORDER BY` is needed on that query either (the fork's code-review below flagged an earlier version of this fix that added a now-redundant `ORDER BY provider_listings.id` too — removed). New `test_service.py::test_match_ranking_ties_break_deterministically_by_listing_id` — two listings identical on every rank_key input (same price/tax/rent), asserts the returned order is ascending listing id. |
| 5 | MINOR | `e2e/borrower-portal/report-matches.spec.ts` depended on a manual `uv run python backend/scripts/freeze_version.py --persona kathleen_mcreynolds` step before every run. | `e2e/global-setup.ts` now runs that script automatically (via `execFileSync("uv", ["run", "python", "backend/scripts/freeze_version.py", ...])`) before Kathleen McReynolds signs in. Made `freeze_version.py` itself idempotent: it now checks for an existing unexpired (`expires_at > now()`), not-superseded `quote_package_versions` row for the persona's application first and reuses it (prints the existing `report_token`) instead of freezing a new one every run. No `fixture_layer` was added to Kathleen's seed persona — CQ-024 and others still see her as `priced`, not `sent`, straight out of `make demo-reset`. |
| 6 | Optional (follow-up, not fixed) | Whether `_build_candidate`'s independent provider calls (tax/insurance/rent-or-STR) could run concurrently. | Left as a follow-up (below) — `AsyncSession` is not safe for concurrent use from multiple coroutines sharing one session, and `_build_candidate` is already called from a plain sequential `for listing in listings` loop sharing the caller's single `db` session, so `asyncio.gather`-ing the three calls *within* one candidate isn't safe without a session-per-call restructure. Not worth the risk for a "nice to have" report surface (Decision 9) at up to 3 candidates. |

Verification for this round: `backend/app/features/matches` 16/16 passed, `backend/app/features/pricing/engine/tests/test_insurance_annual_rate_from_amount.py` 5/5 passed, `uv run ruff check`/`format --check`, `uv run mypy`, `pnpm -r run test`/`lint`/`typecheck`, `pnpm exec prettier --check .`, `alembic heads` — see the updated stage-5 test log above (same commands re-run) and the Playwright re-run below.

### Fork's own `code-review` pass over this round's diff (AGENTS.md stage 6)

Ran a fresh, isolated `code-review` fork over the round-1 diff (its own review, having not written the code). It found no crash-level bugs. Six findings; two fixed here, four accepted as-is with rationale:

| Finding | Action |
| --- | --- |
| `freeze_version.py`'s idempotency check reused any unexpired version without checking it still matched the application's *current* quotes — a re-price within the 21-day window would silently keep serving a stale frozen report. | **Fixed.** The reuse check now also requires `QuotePackage.quote_ids == <the quote_ids the application resolves to right now>` (computed unconditionally before the check, not after). Verified live: froze a version, re-ran `auto_price` to simulate a re-price (new scenario/quotes), ran the script again — it correctly froze a *fresh* version instead of reusing the stale one; ran a third time — reused that new one. `report-matches.spec.ts` still 2/2 after a full `make demo-reset`. |
| The redundant `ORDER BY provider_listings.id` added to `_candidate_listings` (finding 4 above) was undercut by the final sort's own explicit `(rank_key, matched_property_id)` tie-break — two mechanisms for the same guarantee, and the `ORDER BY`'s comment ("`sort` is stable...") was misleading once the tie-break became explicit. | **Fixed.** Removed the `ORDER BY`; kept the explicit tuple tie-break in the final sort as the single source of truth. Re-verified `test_match_ranking_ties_break_deterministically_by_listing_id` still passes. |
| The `PRIMARY`/else branches of the final sort repeated the whole `.sort()` call, differing only in `rank_key`'s sign — a maintenance hazard (STR's branch has no dedicated tie-break test). | **Fixed** as part of the same edit: `sign = Decimal(1) if strategy is StrategyType.PRIMARY else Decimal(-1); candidates.sort(key=lambda c: (sign * c.rank_key, c.match.matched_property_id))` — one call, one place to change the tie-break field. |
| `pricing/scenarios/service.py:171` (`_gather_base_scenario_inputs`, the *subject property's own* scenario-input builder) still divides `insurance_annual / purchase_price` inline instead of calling the new `insurance_annual_rate_from_amount`. | **Not fixed — out of scope.** That file is CQ-011/CQ-017's owned code (pricing scenarios), predates this item, and isn't part of the six batched findings this round addresses; CQ-017's own copy of `insurance_annual_rate_from_amount`'s docstring explicitly cross-references this exact line as a *separate, pre-existing* call site, not something either item was asked to refactor. Changing another item's owned file without being asked risks merge conflicts. Logged here as a real, separate finding for CQ-017/whoever owns that file next. |
| `server_default=sa.text("''")` on `provider_listings.county` means any pre-existing row on a non-empty table silently gets `county=''` (masking, not erroring) instead of a loud failure; `MockTaxClient` would then drop that listing as a candidate with no visible error. | **Accepted, not changed.** This is the literal fix the coordinator's finding 3 asked for (an alternative was an in-migration backfill, not applicable here since `provider_listings` is pure seed data with no "real" historical values to backfill from). `provider_listings` only ever has rows from `seed_providers`/`make demo-reset`, which already writes real `county` values on every row; the empty-string-default path is only reachable via a manual, non-`demo-reset` upgrade of a stale dev DB, which isn't this project's normal workflow. |
| The `NonPositivePriceError` docstring (copied verbatim from CQ-017) references `down_payment_pct_from_amount`, which doesn't exist on this branch — confusing until CQ-017 merges. | **Accepted, not changed.** The coordinator required an exact verbatim copy (same name/signature/docstring/behavior) specifically so the merge keeps one copy without reconciling text differences; editing the docstring here would create exactly the divergence that requirement was meant to avoid. The surrounding block comment already explains why ("copied verbatim from CQ-017... coordinated ... so both branches merge without a rename"). |

Re-verified after these fixes: `backend/app/features/matches` 16/16, full `backend seed` suite 459/459, ruff/mypy clean, `make demo-reset` + Playwright `report-matches.spec.ts` 2/2 live.

## How to test manually

1. `source scripts/worktree-env.sh 6` (or reuse this worktree's `.env`, already slot 6).
   `uv sync && pnpm install`, `uv run alembic upgrade head`, `make demo-reset`.
2. Backend: `uv run uvicorn app.main:app --port 8106` in the background.
3. Portal: `pnpm --filter @cq/borrower-portal exec next dev -p 3206` in the background.
4. Freeze a sent version for Kathleen: `uv run python backend/scripts/freeze_version.py
   --persona kathleen_mcreynolds` — prints the report token. (PR review round 1: `e2e/
   global-setup.ts` now runs this automatically before every Playwright run — step 7 below no
   longer needs it done by hand. This manual step is only for a non-Playwright manual check.)
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
- PR review round 1, finding 6: `_build_candidate`'s three provider calls (tax, insurance,
  rent-or-STR) run sequentially per candidate rather than concurrently. Not fixed —
  `AsyncSession` isn't safe for concurrent use from multiple coroutines sharing one session, and
  making this concurrent would need a session-per-call (or per-candidate) restructure. Worth
  revisiting only if `find_current_matches`'s latency ever matters in practice (up to 3
  candidates today, each already bounded by `simulate_latency`'s mock delay, not real I/O).
