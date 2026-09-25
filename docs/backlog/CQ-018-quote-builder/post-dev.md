# CQ-018 — Post-development notes

## Summary

This item builds the Pricing tab's bottom half. `QuoteBuilderSlot` now renders the quote builder:

- The pipeline's default groups, as quote cards: rate, points (% and $, credits shown green), payment, cash to close, DSCR/cashflow (investment only), investor/product and lock days.
- A single "Recommended" star, which drives the CQ-016 header note rate.
- The Add/Edit overlay, with a live `/quotes/preview` and Save & AutoQuote or Choose manually.
- A sortable manual grid, Compare (2–3 cards, same rows as the borrower comparison table), and the stale banner's working Re-price.
- A `Cannot price: missing {Field}` notice that links to the owning tab.

Backend changes:

- New routes: `GET /applications/{id}/scenarios` (grouped read model), `PUT /scenarios/{id}`, `POST /quotes/{id}/recommend`, `DELETE /quotes/{id}` and `POST /applications/{id}/reprice`.
- Save & AutoQuote now replaces the scenario's quotes instead of appending.
- Every pricing route runs a `missing_field` pre-check.
- Seed: the rate sheet gained an 8-row DSCR ladder, and the LOS down payment now feeds the default groups.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| Routes under `/api/...`, manual pick `{product_row_id}` | Routes under `/api/v1/...`. The manual pick sends `{product, label}` | CQ-013's built routes (plan.md Decision 1). The mock grid has no persisted row ids. |
| 422 `{code: "missing_field", field}` | `{"error": {"code": "missing_field", "message", "details": {"field", "tab", "missing_fields"}}}` | The app's pinned error envelope (Decision 6). `tab` drives the link. |
| `GET .../scenarios` → "scenarios with their quotes" | `{application_id, strategy, recommended_quote_id, groups: [...]}`. Group labels and notes are built server-side. Cards carry display-scale decimals copied from `Quote.computed` | Decision 7: the frontend never computes. |
| Save & AutoQuote "replaces that scenario's quotes" | Par/Buydown rows are **updated in place** (ids stay stable). Manual picks in the scenario are re-priced, not deleted | Deleting would break `applications.recommended_quote_id` and any `quote_packages` reference (FK). The recommendation survives a reprice. |
| Overlay: strategy and FICO as inputs | Shown read-only | Strategy is fixed by the application (`create_scenario` enforces it). FICO is credit-bureau data the OB request reads from `field_values` (Decision 8). |
| Occupancy link: "Borrowers/Property tab" | Links to the Property tab | Decision 6. |
| `DELETE /quotes/{id}` | 409 when a quote package names the quote | FK and snapshot safety. |
| — | `import_from_los` writes `field_values.down_payment_pct`, and `auto_price` uses it | Without it, Daniel Ortiz (5% down) got a single 20% group and AC7 couldn't pass (Decision 3). Marcus is now priced at his LOS 20%. |
| — | `PricedProductRow` gained `monthly_pi` (engine) and `points_pct` | The manual grid's P&I and points columns, without frontend math. |
| — | `quote_engine.discount_points_percent` | `quotes.points` is stored at 3dp as a fraction (0.875 pts → `0.009`), too coarse to display. Points are derived from the quote's own engine output instead. |

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence (test name, command output, screenshot path) |
| --- | --- | --- |
| AC1 | Met | `quotes/builder/tests/test_router.py::test_default_scenario_groups`: Marcus has 2 groups × Par+Buydown, labels "At DSCR 1.00" and "At your DSCR (0.69)". Kathleen has 1 group with the note. `QuoteGroups.test.tsx` AC1 ×2. e2e `quote-builder.spec.ts` "AC1" (after a fresh `make demo-reset`, no user action). `evidence/ac1-marcus-groups.png`. Live: `evidence/api-checks.log`. |
| AC2 | Met | `test_quote_cards_match_engine`: every quote of all 10 seeded personas (≥ 20 cards), card payment, cash to close and points $ == `compute_quote` re-run from the scenario inputs, and == `Quote.computed`. |
| AC3 | Met | `test_autoquote_replaces`: PUT 25% → quotes stale → autoquote → exactly Par+Buydown, down payment 25.00, new par ≤ old; a 2nd autoquote doesn't accumulate. e2e "AC3" (overlay → 25 → Save & AutoQuote; 2 cards, new `priced_at`, par ≤ old). `evidence/ac3-marcus-25-down.png`. |
| AC4 | Met | e2e "AC4": the grid shows 10 rows (≥ 8). Picking "Max Credit" adds a Manual card at 8.250% / -1.500%, and Delete removes it. `evidence/ac4-manual-grid.png`. `test_products_grid_and_manual_pick`. `QuoteBuilder.test.tsx` "Choose manually". |
| AC5 | Met | `test_single_recommended_quote`: recommend A then B → only B starred; summary `note_rate` == B's rate; 2 `quote.recommended` events; delete B → null. `QuoteBuilder.test.tsx` AC5. e2e "AC5": header "Note rate" follows the star, and one pressed star at a time. Live: `api-checks.log` (note_rate None → 7.375). |
| AC6 | Met | `test_autoquote_missing_occupancy`: 422 `missing_field`/Occupancy/tab property for create and reprice; 0 quotes. `QuoteBuilder.test.tsx` AC6 (no PUT is sent). e2e "AC6": the alert text plus a link to `/applications/{id}/property`, and 0 cards. `evidence/ac6-aisha-missing-occupancy.png`. |
| AC7 | Met | `test_default_scenario_groups`: Priya's cards have null DSCR/cashflow/PPP. Daniel: "At 5% down" (MI) and "At 20% down" (no MI, Par only). `QuoteGroups.test.tsx` AC7 ×2 (no `DSCR`/`cashflow`/`prepay` text). e2e "AC7". `evidence/ac7-priya-primary.png`. |
| AC8 | Met | `test_reprice_clears_stale`: override → all stale → reprice → none stale; every `priced_at` later; same ids; the tax reaches `computed`; `has_stale_quotes=false`. `QuoteBuilder.test.tsx` AC8. e2e `reprice-after-override.spec.ts` (Tom & Lisa Brandt). `evidence/ac8-stale-banner.png`, `evidence/ac8-after-reprice.png`. |
| AC9 | Met | `npx react-doctor -y --blocking error` exits 0 (warnings only; see the test log). |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `make test` (pytest backend) | 485 passed |
| Seed tests | `make test` (pytest seed) | 30 passed (persona end statuses unchanged) |
| Lint / types | `make lint` (ruff, ruff format, mypy, eslint, tsc, prettier) | clean, exit 0 |
| Frontend | `make test` (`pnpm -r run test`) | lo-console 109, ui 141, borrower-portal 84, api-client 2: all passed |
| react-doctor | `npx react-doctor -y --blocking error` (apps/lo-console) | exit 0, score 78/100, warnings only (complexity in `QuoteBuilder`/`QuoteCard`/`ScenarioOverlay`, pre-existing `PricingPanel`) |
| E2E | `pnpm exec playwright test e2e/lo-console --workers=1` (slot 8, fresh `make demo-reset`) | 27 passed (8 new CQ-018 + every CQ-016/017 spec) |
| No money math | `quote-builder-no-money-math.test.ts` | 22 passed; every file in `features/quote-builder` is scanned |

## Review findings (stage 6)

| Severity | Finding | Resolution |
| --- | --- | --- |
| Major | `ScenarioOverlay` Add mode: a retry after a failed PUT or autoquote POSTed a new scenario each time, leaving empty groups | A `createdId` ref reuses the scenario the first attempt created. New Vitest test: "Add: retrying Save & AutoQuote after a failed autoquote reuses the created scenario" (1 create, 2 PUTs to the same id). |
| Major | `_reprice_scenario`: a quote whose product left the grid was rebuilt from its old rate/points and marked `stale=False` with a fresh `priced_at` (it looked re-priced) | Now its engine output is recomputed at the refreshed inputs, but it stays `stale=True`, keeps its `priced_at`, and is left out of `quote_ids`. Extended `test_products_grid_and_manual_pick`. |
| Minor | An investment card showed "No prepayment penalty" when the scenario had no PPP set, though OB priced it at the 5-year default | `_prepay_label(None)` → the 5-year default. Only an explicit `0` shows "No prepayment penalty". |
| Major (found in e2e) | Group `<section aria-label="At DSCR 1.00">` made CQ-017's `getByLabel('DSCR')` (a substring match) resolve to 3 elements whenever the builder loaded first | Groups carry `data-testid="quote-group"` and no accessible name, so CQ-017's spec is untouched. The full `e2e/lo-console` run after a fresh `make demo-reset` passes 27/27. |
| Note | Reprice updates Par/Buydown quotes in place even when a draft package names them | By design. A sent package reads its frozen `quote_package_versions` snapshot, so borrowers are unaffected. |

## How to test manually

1. `bash scripts/worktree-env.sh 8`, `make demo-reset`, then start the API on 8108, `make worker` and the LO console on 3108.
2. Sign in as `jordan.lee@clearquote-demo.test` and open Marcus Hale → Pricing. You should see two groups with Par + Buydown each.
3. Star the Buydown. The header Note rate shows 7.375%.
4. Click "Edit scenario" on "At your DSCR", set down payment to 25, then Save & AutoQuote. The cards refresh.
5. Click "Edit scenario" → Choose manually, and pick a row. A Manual card appears. Delete it.
6. Override the tax rate in the panel. The stale banner appears; click Re-price and it clears.
7. Open Aisha Coleman → Pricing → Add scenario → Save & AutoQuote. You should see "Cannot price: missing Occupancy" with a link to the Property tab.

## What CQ-019 needs

- **Recommended quote:** `applications.recommended_quote_id`, also returned as `recommended_quote_id` by `GET /api/v1/applications/{id}/scenarios` and as `recommended: true` on its card. It is null until the LO stars a quote. No seeded persona has one after `make demo-reset`, so CQ-019's default draft should fall back to the first group's Par.
- **Group order for the default draft:** the `groups` array order is canonical: `created_at`, then the assumed-DSCR-1.00 group first (investment) or the lower down payment first (primary), then id. Within a group, cards are ordered Par, Buydown, then Manual picks. Suggested default package: recommended quote (or first group's Par), then the remaining Par/Buydown in array order, up to 3.
- Quote ids survive reprice and Save & AutoQuote (in-place update), so a draft package's `quote_ids` stay valid. `DELETE /quotes/{id}` returns 409 for a quote named by any `quote_packages` row.
- `quotes.stale` is cleared by `POST /applications/{id}/reprice`, which is the call for "Send blocks when any quote is stale".

## Follow-ups

- `quotes.points` is `Numeric(6,3)` as a fraction, which loses precision (0.875 pts is stored as 0.009). Cards use the engine-derived value. A migration to `Numeric(8,5)` would fix the column itself.
- The OB request builder uses `applications.requested_price`, not the scenario's own purchase price, so a price edit in the overlay changes the engine numbers but not the mock grid's loan-amount-based rows. This is harmless with the current mock (price-agnostic rate sheet).
- The mock adapter ignores `DesiredLockDays`, so overlay lock-days changes are stored and sent but don't change the demo grid.
