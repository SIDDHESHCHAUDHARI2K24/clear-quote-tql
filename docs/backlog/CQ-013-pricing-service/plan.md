# CQ-013 Pricing service & API — plan

## Decisions & questions (stage 1 gap check)

Small gaps decided below (data available); none rose to a Kaneo `needs-input` big gap.

- **Decision 1 — `DEV_LO_ID` setting.** `core/config.py`'s `Settings` has no field for it yet (CQ-002 spec names CQ-013 as the introducing item). Added `dev_lo_id: str | None = None` (reads env `DEV_LO_ID`). `.env`/`.env.example` get the key.
- **Decision 2 — shared test fixtures.** `backend/app/integrations/conftest.py`'s `_fake_valkey` and `_clean_integration_calls` autouse fixtures move up to `backend/conftest.py` so `pricing`/`quotes` tests (which also exercise mock adapters) get them without duplicating. `integrations/conftest.py` is deleted; nothing else was in it.
- **Decision 3 — CQ-012 is merged** (orchestrator update): `write_flag`/`resolve_flag` live at `app.features.applications.verification.service` with signatures `write_flag(db, application_id, tab, field_key, rule, severity) -> Flag` and `resolve_flag(db, application_id, field_key, rule) -> Flag | None`. No local shim needed. Used symmetrically: `validate_ob_required_fields` writes a `blocking` flag per missing OB field (`rule="ob_required_field"`) on failure and resolves every possible OB field's flag on success; `run_two_pass_dscr` writes/resolves `rule="dscr_bucket_unstable"` on `field_key="dscr_ratio"`.
- **Decision 4 — `ConfigSnapshot` source.** No item wires `settings` table rows into `ConfigSnapshot` yet; CQ-013 uses `ConfigSnapshot()` defaults everywhere (preview, scenario create, auto-price). A later item can add a settings-loader without changing this item's function signatures.
- **Decision 5 — HOA data source.** No adapter or seeded table returns a real HOA fee (catalog says "Redfin/Zillow/listing", none of which are modeled). `enrich_pricing_fields` always writes `hoa_fee_monthly = 0.00` with `source=FieldSource.DEFAULT`, for every property type. Revisit when a real HOA source is modeled.
- **Decision 6 — beds param for Rent/STR clients.** `RentClient.get_market_rent`/`StrClient.get_str_revenue` take `beds: int`; `properties` has no bedroom count column. Uses `Property.number_of_units` as the proxy.
- **Decision 7 — purchase price for enrichment/default pricing.** "Borrower's requested amount from the application; else max purchasing power" (system-design) — no purchasing-power engine exists in any merged item. Uses `Application.requested_price` only; if it's `None`, `auto_price`/`enrich_pricing_fields` raise `ValidationAppError` (a real, if rare, gap — no fallback exists to compute).
- **Decision 8 — down payment defaults for auto-pricing.** Primary 20%, Investment 25%, per system-design's default table (LO overrides via `ScenarioCreateRequest.down_payment_pct` on the manual path).
- **Decision 9 — `ScenarioCreateRequest` fields.** Limited to the 5 LO-owned inputs system-design lists (purchase price, down payment %, PPP, strategy — note rate is chosen later, per-row, not at scenario-creation time) plus optional `label`. FICO, tax, insurance, HOA, rent/STR are enrichment-owned and read from `field_values` server-side, not accepted from the client.
- **Decision 10 — `create_scenario` returns `quotes: []`.** It persists the scenario and (LTR/STR only) runs `run_two_pass_dscr` purely to resolve `dscr_bucket`; it does not create `Quote` rows. Quotes come from `/autoquote` or `/quotes` (manual), matching the Quote Builder's actual two-step UI (create scenario, then Save & AutoQuote or Choose Manually).
- **Decision 11 — `draft_default_quote_set` scope.** No new persisted "quote set"/recommendation table is in CQ-007's model list for this item (`quote_packages.recommended_quote_id` is CQ-019/22's Send-tab job). Implemented as a thin confirmation: loads the `Quote` rows named in the `PricingResult` and returns them as `QuoteSetResult(quote_ids=...)`, satisfying CQ-011's activity contract without inventing new tables.
- **Decision 12 — DSCR two-pass "price at a bucket" callback.** `run_two_pass_dscr` takes a `price_par_at_dscr: Callable[[Decimal], Awaitable[PricedProductDTO]]` callback rather than calling `PricingClient` itself, so AC8's unit test can inject a fixture pricer with no DB/OB involved; production callers (`create_scenario`, `create_default_scenarios`) close over the real `MockPricingClient` call + `build_ob_search_request`. Representative DSCR values sent to OB per assumed bucket: `BELOW_1_00→0.99`, `ONE_TO_1_25→1.00`, `GE_1_25→1.25`.

## Why / what

Wires CQ-008's pure engine to real data: enrichment writes sourced `field_values`, OB required-field validation surfaces `PRICING_VALIDATION_ERROR` as HTTP 422, default scenario sets + Save&AutoQuote + manual grid + DSCR two-pass loop persist `scenarios`/`quotes`, and `/quotes/preview` gives the LO console/borrower portal a fast (<300ms) recompute path. Also exposes the two function names CQ-011's workflow and CQ-010's demo-reset call synchronously today.

## Files touched

```
backend/app/core/config.py                          (+dev_lo_id)
backend/app/core/registry.py                         (+2 routers)
backend/conftest.py                                   (+moved fixtures)
backend/app/integrations/conftest.py                  (deleted)
backend/app/features/pricing/enrichment/{__init__,schemas,service,router}.py
backend/app/features/pricing/enrichment/tests/{__init__,test_enrichment,test_field_value_override}.py
backend/app/features/pricing/scenarios/{schemas,deps,ob_request,dscr_loop,service,router}.py
backend/app/features/pricing/scenarios/tests/{test_quotes_preview_perf,test_ob_validation,
  test_default_scenarios_investment,test_default_scenarios_primary,test_autoquote_selection,
  test_dscr_two_pass_loop,test_products_grid,test_manual_quote,test_auth_stub,conftest}.py
backend/app/features/quotes/builder/{schemas,service}.py
backend/app/features/quotes/builder/tests/test_draft_quote_set.py
.env / .env.example                                   (+DEV_LO_ID)
packages/api-client/*                                 (regenerated)
```

## Tasks (single-agent, sequential — no wave split needed at this size)

1. Core plumbing: `dev_lo_id` setting, conftest fixture move, `.env`.
2. `pricing/enrichment`: schemas, service (`enrich_pricing_fields`, override/revert), router. Tests AC2/AC3.
3. `pricing/scenarios`: schemas, `deps.get_current_lo_stub`, `ob_request.build_ob_search_request`, `dscr_loop.run_two_pass_dscr`, `service` (`create_scenario`, `create_default_scenarios`, `select_par_and_buydown`, `auto_price`), router. Tests AC1, AC4-AC11.
4. `quotes/builder.service.draft_default_quote_set` + test.
5. Register routers, `ruff`/`mypy`/`pytest` full pass (AC12), `make api-client`.
6. `post-dev.md`, commit, push, CI.

## Acceptance criteria → test map

| AC | Test |
| --- | --- |
| AC1 | `pricing/scenarios/tests/test_quotes_preview_perf.py` |
| AC2 | `pricing/enrichment/tests/test_enrichment.py` |
| AC3 | `pricing/enrichment/tests/test_field_value_override.py` |
| AC4 | `pricing/scenarios/tests/test_ob_validation.py` |
| AC5 | `pricing/scenarios/tests/test_default_scenarios_investment.py` |
| AC6 | `pricing/scenarios/tests/test_default_scenarios_primary.py` |
| AC7 | `pricing/scenarios/tests/test_autoquote_selection.py` |
| AC8 | `pricing/scenarios/tests/test_dscr_two_pass_loop.py` |
| AC9 | `pricing/scenarios/tests/test_products_grid.py` |
| AC10 | `pricing/scenarios/tests/test_manual_quote.py` |
| AC11 | `pricing/scenarios/tests/test_auth_stub.py` |
| AC12 | `ruff check` / `mypy` on both packages |
| (extra, orchestrator req.) | resolve-direction tests for `ob_required_field` and `dscr_bucket_unstable` flags, in `test_ob_validation.py` / `test_dscr_two_pass_loop.py` |

## Progress checklist

- [x] Stage 1 gap check
- [x] Stage 2 plan
- [x] Stage 3/4 implementation
- [x] Stage 5 verification log (post-dev.md)
- [x] Stage 7 acceptance checklist (post-dev.md)
- [x] Stage 8 commit + push + CI

## Decisions & questions — addendum (mid-flight)

- **Decision 13 (bug fix, not a deviation).** `PricedProductDTO.note_rate` is percent-scale (e.g. `7.125` meaning 7.125%, matching `provider_rate_sheet.base_rate`); `ScenarioInputs.note_rate` is a 0-1 fraction like every other engine rate field. `dscr_loop.inputs_with_priced_product` (shared by `dscr_loop.py` and `service.py`, exported rather than duplicated after this was caught) divides by 100 at that one boundary. `discount_points_pct` needed no conversion — it's already a fraction on both sides.
- **Orchestrator update applied:** CQ-012 merged before this item finished; `write_flag`/`resolve_flag` at `app.features.applications.verification.service` used directly (no shim needed, Decision 3 above already anticipated the exact signature). Added the resolve-direction tests requested: `test_ob_validation.py::test_fixing_the_field_resolves_the_flag` and `test_dscr_two_pass_loop.py::test_stable_run_resolves_a_previously_raised_unstable_flag`.
