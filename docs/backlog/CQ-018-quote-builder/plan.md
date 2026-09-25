# CQ-018 — Implementation plan

Written by the agent in stages 1–3. Every acceptance criterion maps to a test before coding.

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Spec route names vs. CQ-013's built routes | Decided: keep CQ-013's built routes as they are (`POST /applications/{id}/scenarios`, `GET /scenarios/{id}/products`, `POST /scenarios/{id}/autoquote`, `POST /scenarios/{id}/quotes`, all under `/api/v1`). Manual pick sends the full product row (`{product, label}`) rather than `{product_row_id}`, because the mock grid has no persisted row ids. Added the missing ones: `GET /applications/{id}/scenarios`, `PUT /scenarios/{id}`, `DELETE /quotes/{id}`, `POST /quotes/{id}/recommend`, `POST /applications/{id}/reprice`. |
| 2 | Decision | AC1 buydown risk: no Buydown candidate for DSCR buckets `BELOW_1_00` and `ONE_TO_1_25`, and Marcus's grid had only 2 rows (AC4 needs ≥ 8) | Decided: added 8 bucket-agnostic DSCR rate-sheet rows to `seed/providers/rate_sheet.yaml` (Harborline Capital and Keystone Investor Lending): a ladder from 1.5 points to a 1.5-point credit, with 5-year PPP, FICO ≥ 680 and LTV ≤ 80. Each price is more than 0.500 from par, so no persona's par row changes, and neither do its DSCR bucket or end status (verified). The Buydown is 7.375% at 1.000 point. The `8 <= rows <= 15` bound in `seed/tests/test_provider_rows_seeded.py` is now `<= 25`. No persona special-casing in code. |
| 3 | Decision | AC7: Daniel Ortiz (5% down in LOS) got one group, because `auto_price` always priced at the 20%/25% default and ignored the LOS down payment | Decided: `import_from_los` writes a `down_payment_pct` `field_values` row (source `encompass`) when the loan file has one. `create_default_scenarios` reads it when no down payment is passed, and falls back to the old defaults otherwise. Two small edits outside the owned files (`applications/service.py`, `pricing/scenarios/service.py`). Effect: Daniel gets 5% (Par + Buydown) and 20% (Par). Marcus is priced at his LOS 20% (DSCR 0.69, still `BELOW_1_00`, 2 groups), which makes AC3's "edit to 25% down" an actual change. Persona end statuses are unchanged. |
| 4 | Decision | Save & AutoQuote semantics (AC3 says "replaces") | Decided: `POST /scenarios/{id}/autoquote` now replaces the scenario's Par/Buydown quotes instead of appending. It first refreshes the scenario's enrichment-owned inputs (tax, insurance, HOA, rent) from `field_values` and prices, so a pricing error leaves the quotes untouched. Then it updates the existing Par/Buydown rows **in place** with the new pick (insert if missing; a leftover or duplicate auto quote is deleted unless a quote package names it). Ids stay stable, so the recommendation and any `quote_packages` reference survive (a delete would violate the `quote_packages.recommended_quote_id` FK). Manual picks in that scenario are re-priced: the same investor/product row from the fresh grid, or the same rate/points when that row is gone. `DELETE /quotes/{id}` returns 409 for a quote named by a package. |
| 5 | Decision | Reprice (AC8) | Decided: `POST /applications/{id}/reprice` runs Decision 4's replace for every scenario of the application. It keeps each scenario's LO inputs and assumed DSCR bucket, clears `stale`, and sets `priced_at = now` on every quote. It writes one `quotes.repriced` activity event. |
| 6 | Decision | 422 shape `{code: "missing_field", field}` | Decided: it uses the app's pinned error envelope `{"error": {"code": "missing_field", "message": "Cannot price: missing Occupancy", "details": {"field": "Occupancy", "missing_fields": [...], "tab": "property"}}}`. A pre-check (`ensure_priceable`) builds the OB request and checks the adapter's required-field lists before any write, on: create scenario, PUT, autoquote, products, manual pick and reprice. The OB-field→tab map: Occupancy/PropertyType/NumberOfUnits/State/County/ZipCode → property; RepresentativeFICO → credit; everything else → pricing. Occupancy goes to the Property tab (the spec's "Borrowers/Property") because the Property tab owns property use. |
| 7 | Decision | `GET /applications/{id}/scenarios` response shape | Decided: it returns `{application_id, strategy, recommended_quote_id, groups: [...]}` instead of a bare list, so the page has the strategy gate and the recommendation in one call. Each group carries a server-built `label` ("At DSCR 1.00", "At your DSCR (0.69)", "At 5% down") and `note` ("Your DSCR prices the same as 1.00" when an investment app has one group whose actual bucket equals the assumed 1.00 bucket). Each card carries display-ready decimals (`rate_pct`, `points_pct` at percent scale, 3dp; `points_amount`, `monthly_payment`, `cash_to_close`, `dscr_ratio`, `monthly_cashflow`) copied from `Quote.computed`. The frontend only formats; it never computes. |
| 8 | Decision | Overlay inputs | Decided: editable inputs are purchase price, down payment %, PPP years (investment), lock days, and the assumed DSCR bucket (investment). Strategy and FICO are shown read-only. Strategy is the application's occupancy/strategy, which `create_scenario` already enforces. FICO is a credit-bureau `field_values` value that the OB request builder reads, so an edit would never reach pricing. Lock days go into the scenario's inputs JSON and the OB request's `DesiredLockDays`. The mock adapter does not filter by lock, so this changes nothing in the demo grid. |
| 9 | Decision | CQ-017 panel edits vs. overlay persistence | Decided: the panel's price and down-payment edits stay preview-only (CQ-017). The overlay's Save & AutoQuote persists inputs via `PUT /scenarios/{id}` (or `POST .../scenarios` for Add), then calls `/autoquote`. The overlay opens pre-filled from the scenario, not from the panel's unsaved draft. |
| 10 | Decision | Stale banner source | Decided: `QuoteBuilderSlot` shows the banner when its own `GET .../scenarios` data has any `stale` quote, or, before the first load, from the `hasStaleQuotes` prop. After a reprice it refetches, so the banner clears without editing `PricingPanel.tsx`. The panel remounts the slot on every override/revert (`load()` shows the skeleton), so fresh stale state always arrives. After recommend, delete and reprice, the builder calls `useWorkspace().refetch()` so the CQ-016 header note rate updates. |
| 11 | Decision | Recommend | Decided: `POST /quotes/{id}/recommend` sets `applications.recommended_quote_id` (a single column, so there is only ever one) and writes a `quote.recommended` activity event. Starring the already-recommended quote again is a no-op (no un-recommend route; the spec lists none). `DELETE /quotes/{id}` nulls the column when it pointed at the deleted quote, and writes `quote.deleted`. |
| 12 | Decision | Compare table | Decided: `ComparisonTable` (`packages/ui`) takes the full `ReportOption` view model (hero, cashflow, …), which a quote card does not have. `CompareTable.tsx` reuses its exact rows (Rate, Points, Down payment, Prepayment penalty†, Monthly payment, Cash to close, Monthly cashflow†, DSCR†; † investment only) against the card read model. |
| 13 | Decision | PUT of an Aisha-style unpriceable app | Decided: every write route runs `ensure_priceable` first, so a missing field returns 422 with nothing written. For Aisha (no scenarios, since the pipeline stopped), the overlay's Add path hits `POST .../scenarios` → 422 → "Cannot price: missing Occupancy" with a link to `/applications/{id}/property`. |

No big gaps.

## Why

The pipeline already prices default scenarios, but the LO has nowhere to see, compare, edit, recommend or re-price them. This item is the bottom half of the Pricing tab. It also sets `recommended_quote_id`, which the CQ-016 header note rate and CQ-019's default package read.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Backend builder routes | `backend/app/features/quotes/builder/{router,schemas,service}.py` (new router + schemas; service gains list/update/delete/recommend/reprice), `backend/app/core/registry.py` |
| Scenarios additions | `backend/app/features/pricing/scenarios/{service,router}.py` (autoquote replace + pre-check; LOS down payment default; lock days in OB overrides) |
| LOS down payment | `backend/app/features/applications/service.py` (one `field_values` write) |
| Seed | `seed/providers/rate_sheet.yaml` (+8 rows), `seed/tests/test_provider_rows_seeded.py` (row bound) |
| Tests (backend) | `backend/app/features/quotes/builder/tests/test_*.py` |
| API client | `packages/api-client` (regenerated) |
| Frontend | `apps/lo-console/src/features/pricing/QuoteBuilderSlot.tsx`, `apps/lo-console/src/features/quote-builder/**` |
| E2E | `e2e/lo-console/quote-builder.spec.ts`, `e2e/lo-console/reprice-after-override.spec.ts` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Seed rate-sheet rows + LOS down payment default | — | rate_sheet.yaml, seed test, applications/service.py, scenarios/service.py (default) | seed tests, `test_default_scenario_groups` |
| T2 | Builder schemas + service + router (list, PUT, delete, recommend, reprice, missing-field pre-check, autoquote replace) | T1 | quotes/builder/**, scenarios/router.py, registry.py | `test_default_scenario_groups`, `test_quote_cards_match_engine`, `test_single_recommended_quote`, `test_autoquote_missing_occupancy`, `test_reprice_clears_stale`, `test_autoquote_replaces`, `test_scope_404` |
| T3 | `make api-client` | T2 | packages/api-client | tsc |
| T4 | Frontend: groups, cards, overlay, manual grid, compare, stale banner, error state | T3 | QuoteBuilderSlot.tsx, features/quote-builder/** | `QuoteGroups.test.tsx`, `QuoteCard.test.tsx`, `ScenarioOverlay.test.tsx`, `quote-builder-no-money-math.test.ts` |
| T5 | Playwright + evidence | T4 | e2e/lo-console/quote-builder.spec.ts, reprice-after-override.spec.ts | e2e |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1, T2 | Seed data and API contract first |
| 2 | T3 | api-client from the final contract |
| 3 | T4 | Consumes the generated client |
| 4 | T5 | Needs the running stack |

(Run sequentially by one agent. No two tasks touch the same file in one wave.)

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `test_default_scenario_groups` (Marcus: 2 groups × Par+Buydown; Kathleen: 1 group + note), `QuoteGroups.test.tsx` |
| AC2 | `test_quote_cards_match_engine` (every seeded persona quote: card payment/cash to close == `compute_quote` re-run) |
| AC3 | `test_autoquote_replaces` + `e2e/lo-console/quote-builder.spec.ts` "AC3" |
| AC4 | `e2e/lo-console/quote-builder.spec.ts` "AC4" (+ `test_products_grid_has_8`) |
| AC5 | `test_single_recommended_quote` + `QuoteCard.test.tsx` star toggle |
| AC6 | `test_autoquote_missing_occupancy` + e2e "AC6" |
| AC7 | `test_default_scenario_groups` (Priya/Daniel) + `QuoteGroups.test.tsx` primary gating |
| AC8 | `test_reprice_clears_stale` + `e2e/lo-console/reprice-after-override.spec.ts` |
| AC9 | `npx react-doctor -y --blocking error` |

## Progress

- [x] T1 (rate ladder + LOS down payment; seed tests 30 passed)
- [x] T2 (builder routes; `quotes/builder/tests/test_router.py` 17 passed)
- [x] T3 (`make api-client`)
- [x] T4 (UI; lo-console Vitest 108 passed; react-doctor exit 0)
- [x] T5 (Playwright 27 passed incl. 8 new; evidence/)

Added during stage 4 (logged): `PricedProductRow.monthly_pi`/`points_pct` for the manual grid's P&I/points columns; `quote_engine.discount_points_percent` (the `quotes.points` column is 3dp and too coarse to display); `QuoteCardRead.note_rate`/`discount_points_pct` and `ScenarioGroupRead.engine_inputs` so the overlay's live preview posts engine-scale values without frontend math.
