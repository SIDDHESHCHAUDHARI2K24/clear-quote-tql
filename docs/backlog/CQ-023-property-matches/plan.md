# CQ-023 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Catalog says `buy_box_market_cities`; the `Property` model (CQ-007) built it as `buy_box_metros`. | Use the built name `buy_box_metros` throughout (matches AGENTS.md's steer to log, not rename, a built field). |
| 2 | Decision | Data-field-catalog §4 has no listing attribute for "owner-occupant listings" (primary's strategy-fit rule); the mock inventory is generic single-family homes with no distinct primary/investment split. | Primary strategy fit == the full candidate set (price band + geography only, no extra filter) — there is nothing in the catalog or seed to filter *out* for a primary buyer. Only STR gets a real new filter (`str_permitted`), since the catalog explicitly calls out "STR-zoned community" taglines and spec.md AC5 names it. No `owner_occupant` column added. |
| 3 | Decision | `ProviderListing` has no `county`, needed for `MockTaxClient.get_tax_rate(state, county)` per listing. | Add `provider_listings.county` (`String`, not null) in a new migration chained off `bbd0e3150264`. Backfilled on all 10 existing seed rows from `seed/providers/tax_rates.yaml`'s matching `(state, county)` row (same state already implies the same county in this seed set — one county per state). |
| 4 | Decision | `ProviderListing` has no STR-eligibility flag, needed for "STR → ... STR-permitted listings only" (spec.md). | Add `provider_listings.str_permitted` (`Boolean`, default `false`) in the same migration. |
| 5 | Decision | Rent/STR-revenue provider fixtures (`seed/providers/rents.yaml`/`str_revenue.yaml`) are keyed `(zip, beds)` but only ever seeded at `beds=1` — the convention established by CQ-013 (`seed/tests/test_personas_match_engine.py`'s own comment: "Keyed on `Property.number_of_units` ... not the persona table's own Beds column"), because every seeded subject property is `single_family` (1 unit). Listings carry a real bedroom count (2–4) that has no rent/STR row. | Call `MockRentClient`/`MockStrClient` with `beds=1` for every listing (all `property_type=single_family`, i.e. 1 unit), not the listing's own `beds` column — same convention, not a new one. Logged here since it reads oddly without this note. |
| 6 | Decision | spec.md names the service function `find_matches(application, recommended_option) -> list[Match]`; the coordinator's brief (D4, phase-p3-p4-plan.md) names the CQ-019/CQ-020 hook `compute_matches_for_package(db, *, application, recommended_quote) -> list[ReportMatchInput]`. | Build one function, `compute_matches_for_package`, as the coordinator's brief pins it (it's the one CQ-019/CQ-020 will actually call) — it *is* `find_matches`, spec.md's name was descriptive, not binding syntax. No separate `find_matches` wrapper. |
| 7 | Decision | `applications.recommended_quote_id` (P3/P4 foundation column) is only ever set by CQ-018 (Quote Builder "recommend" endpoint), which hasn't merged into `phase-p3-p4` yet — every seeded persona (including Kathleen) has it `NULL` today. `GET /applications/{id}/matches` needs *some* current recommended quote to run the engine against. | `_resolve_recommended_quote`: prefer `application.recommended_quote_id` when set; else take the application's earliest-created `Scenario` (by `created_at`, `id` tiebreak) and its `Quote` labelled `"Par"` (falling back to the first quote if no `"Par"` label exists). This mirrors `seed/loader.py::apply_send_fixture`'s own `quote_ids[0]` convention (the first group's Par quote) without depending on insert-order timestamps being distinct. Once CQ-018 merges and starts setting the column, this fallback simply stops being hit for newly-recommended applications. |
| 8 | Decision | No ranking rule is specified for `primary` matches (spec.md only pins LTR-by-cashflow and STR-by-DSCR). | Rank primary matches by ascending `total_monthly_payment` (cheapest payment first) — the one number every buyer cares about, computed by the engine like everything else. |
| 9 | Decision | A provider call (`MockTaxClient`/`MockRentClient`/`MockStrClient`/`MockInsuranceClient`) can raise (forced-fail toggle, or a missing seeded row for a listing's zip/state). | A candidate listing that raises during enrichment is skipped (best-effort), not a 500 for the whole matches list — matches.md is a "nice to have" surface, not a blocking pipeline stage. Logged so `record_call`'s own failure logging still captures it. |
| 10 | Decision | `ReportMatchInput`/`ReportMatch` (CQ-021, my owned-additive files) need the spec's new fields. | Extend both additively: `total_monthly_payment`, `rent_estimate`/`rent_label` (the pre-expense-ratio gross figure + "Market rent (LTR)"/"Gross STR revenue" label, same convention as `CashflowTable.gross_amount`/`rent_label`), `monthly_cashflow`, `cash_to_close`, `cap_rate_pct`, `year1_tax_savings` — all `None` for primary. |

No big gaps raised.

## Why

A TBD borrower's report currently shows an empty matches section forever (`ReportMatchesSlot` renders `null`, `viewModel.matches` always `[]`). This item makes it real: 3 listings, run through the exact same `quote_engine` the borrower's own quote used, ranked by the number that matters for their strategy.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Migration | `alembic/versions/<rev>_provider_listings_county_str_permitted.py` (new) |
| Listings model | `backend/app/integrations/property_search/models.py` (add `county`, `str_permitted`) |
| Engine | `backend/app/features/pricing/engine/quote_engine.py` (`match_floor_price`/`match_ceiling_price`, own block) + tests |
| Report contract | `backend/app/features/quotes/report/inputs.py`, `schemas.py`, `builder.py` (additive match fields) + tests |
| Match service | `backend/app/features/matches/{router,schemas,service}.py` (new) + tests |
| Freeze hook | `backend/app/features/portal/reports/versions.py` (call `compute_matches_for_package`) |
| Registry | `backend/app/core/registry.py` (register `app.features.matches.router`) |
| Fixtures | `backend/scripts/build_report_fixtures.py` (regenerate with match fields) |
| Seed | `seed/providers/listings.yaml` (add Kathleen in-band ×2, boundary ×2, STR-permitted Tampa ×2) |
| UI components | `packages/ui/src/report/{MatchCard,MatchList}.tsx` + tests + `index.ts` exports |
| Portal slot | `apps/borrower-portal/src/features/report/ReportMatchesSlot.tsx` |
| Gallery | both apps' `/gallery/report` pages (optional `renderMatches` visual check) |
| E2E | `e2e/borrower-portal/report-matches.spec.ts` |
| Dev script | `backend/scripts/freeze_version.py` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Migration: `provider_listings.county`/`str_permitted` | — | migration, `property_search/models.py` | `backend/tests/test_schema.py` (existing FK/table scan picks it up) |
| T2 | `quote_engine.match_floor_price`/`match_ceiling_price` | — | `quote_engine.py` | `test_price_band_boundaries` |
| T3 | Seed: county backfill + new listings | T1 | `listings.yaml`, `tax_rates.yaml` (Orange Co not needed) | `seed/tests` (existing loader tests still pass; row count) |
| T4 | Extend `ReportMatchInput`/`ReportMatch`/builder | — | `inputs.py`, `schemas.py`, `builder.py` | `quotes/report/tests/test_builder.py` (matches formatting) |
| T5 | `matches` service + router + schemas | T1, T2, T4 | `features/matches/**` | `test_matches_kathleen`, `test_match_numbers_match_engine`, `test_no_matches_with_address`, `test_matches_toggle_off`, `test_match_ranking_by_strategy`, `test_price_band_boundaries` (service-level) |
| T6 | Freeze hook | T5 | `portal/reports/versions.py` | `test_matches_frozen_in_version` |
| T7 | Registry | T5 | `core/registry.py` | (covered by router tests) |
| T8 | Rebuild fixtures | T4 | `build_report_fixtures.py`, fixture JSON | existing fixture/AC5 scan tests |
| T9 | `MatchCard`/`MatchList` | T4 (types) | `packages/ui/src/report/*` | Vitest |
| T10 | `ReportMatchesSlot` fill-in | T9 | portal slot | Vitest + Playwright |
| T11 | E2E spec + dev freeze script | T6, T10 | `e2e/...`, `backend/scripts/freeze_version.py` | Playwright |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | Migration and engine additions are the contract everything else reads |
| 2 | T3, T4 | Seed data and report-contract additions, independent of each other |
| 3 | T5 | Needs T1/T2/T4 |
| 4 | T6, T7, T8, T9 | Needs T5 (hook, registry, fixtures) / T4 (types) |
| 5 | T10 | Needs T9 |
| 6 | T11 | Needs T6, T10 |

Single-agent execution (no parallel subagents dispatched for this item — the surface area is one coherent backend+frontend vertical slice with a strict dependency chain, not independent units).

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `backend/app/features/matches/tests/test_service.py::test_matches_kathleen` |
| AC2 | `backend/app/features/matches/tests/test_service.py::test_match_numbers_match_engine` |
| AC3 | `backend/app/features/matches/tests/test_router.py::test_no_matches_with_address` |
| AC4 | `backend/app/features/matches/tests/test_service.py::test_matches_toggle_off` |
| AC5 | `backend/app/features/matches/tests/test_service.py::test_match_ranking_by_strategy` |
| AC6 | `backend/app/features/pricing/engine/tests/test_quote_engine.py::test_price_band_boundaries` (pure) + `backend/app/features/matches/tests/test_service.py::test_price_band_boundaries_excludes_listings` (DB-level, Kathleen's 69%/101% boundary listings) |
| AC7 | `backend/app/features/portal/reports/tests/test_versions.py::test_matches_frozen_in_version` |
| AC8 | `packages/ui/src/report/MatchList.test.tsx` (responsive columns via CSS class assertions) + `e2e/borrower-portal/report-matches.spec.ts` (375px/1120px) + `react-doctor` |

## Progress

- [x] T1–T11 (see post-dev.md for evidence)
