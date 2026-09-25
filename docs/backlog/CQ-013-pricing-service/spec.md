# CQ-013 Pricing service & API

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-008, CQ-009 |
| Kaneo task | CQ-013 in Kaneo (task id `q2x1i5vvr84ipy6yctbu6bpk`) |
| Branch | `cq-013-pricing-service` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

The LO can price an application: fields are enriched with sources, Optimal Blue returns products through the mock, default scenarios are auto-priced, and the LO previews or edits a breakdown in under 300 ms — the same numbers CQ-008's engine computes, now wired to data and exposed over the API.

## Scope

Enrichment (tax, insurance, HOA, rent/STR) into `field_values` with source + override/revert; OB required-field validation; scenario and quote persistence; default scenario sets; Save & AutoQuote; manual product grid; DSCR two-pass loop; `/quotes/preview`.

**Module paths (binding)**

```
backend/app/features/pricing/
  engine/          # CQ-008, consumed not modified
  enrichment/
    router.py      # field-value override/revert routes
    service.py      # enrich_pricing_fields(), validate_ob_required_fields()
    schemas.py       # FieldValueRead, FieldValueOverrideRequest
    tests/
  scenarios/
    router.py       # /quotes/preview, /applications/{id}/scenarios, /scenarios/{id}/products, /scenarios/{id}/autoquote, /scenarios/{id}/quotes
    service.py       # create_scenario(), create_default_scenarios(), select_par_and_buydown()
    dscr_loop.py     # run_two_pass_dscr()
    ob_request.py    # build_ob_search_request() -> assembles the OB payload; validation happens in CQ-009's PricingClient
    schemas.py        # QuotePreviewRequest/Response, ScenarioCreateRequest/Read, PricedProductRow, AutoQuoteResponse, QuoteRead, ManualQuoteCreateRequest
    deps.py            # get_current_lo_stub() — auth stub, see Decision
    tests/
```

**Routes (binding; all under `deps.get_current_lo_stub` until CQ-014 — see Decision)**

| Method & path | Request | Response |
| --- | --- | --- |
| `POST /quotes/preview` | `QuotePreviewRequest` (= `ScenarioInputs` fields, no persistence) | `QuotePreviewResponse` (= `QuoteComputation` fields) |
| `POST /applications/{application_id}/scenarios` | `ScenarioCreateRequest` (pricing inputs + optional `label`) | `ScenarioRead` (id, inputs, config_snapshot, dscr_bucket, `quotes: list[QuoteRead]`) |
| `GET /scenarios/{scenario_id}/products` | — | `list[PricedProductRow]` (8–15 OB rows, "Choose manually" grid) |
| `POST /scenarios/{scenario_id}/autoquote` | — | `AutoQuoteResponse {par: QuoteRead, buydown: QuoteRead \| None}` |
| `POST /scenarios/{scenario_id}/quotes` | `ManualQuoteCreateRequest` (chosen `PricedProductRow` + `label`) | `QuoteRead` |
| `PATCH /applications/{application_id}/field-values/{field_key}` | `FieldValueOverrideRequest {value}` | `FieldValueRead` |
| `POST /applications/{application_id}/field-values/{field_key}/revert` | — | `FieldValueRead` (restored to `source`) |

`field_key` for the override routes is one of the catalog names this item enriches: `property_tax_annual_rate`, `homeowners_ins_annual`, `hoa_fee_monthly`, `market_rent_ltr`, `gross_annual_revenue_str`.

**Enrichment.** `enrich_pricing_fields(application_id)` calls `TaxClient`, `InsuranceClient`, and (by strategy) `RentClient` or `StrClient` (CQ-009 Protocols) and writes one `field_values` row per field, `source` set to CQ-007's `FieldSource` enum value (owner: CQ-007) — not a display string: `smartasset` (tax), `steadily` (insurance), `rentcast` (LTR rent), `airdna` (STR revenue), `property_search` or `default` ($0) for `hoa_fee_monthly`. (The LO Console renders the human-readable label — "SmartAsset", "Steadily", etc. — from the `SourceBadge` component's own display mapping (CQ-005/CQ-021), not from this stored value.) Idempotent: skips any `field_key` where `overridden_by is not null`. Called by the Temporal enrich activity (CQ-011) and by a manual "re-enrich" action from the pricing panel.

**OB required-field validation.** `enrichment/service.py::validate_ob_required_fields(application_id) -> bool` is the function the Temporal Validate stage (CQ-011) and `demo-reset` (CQ-010) call by name; it builds the request via `scenarios/ob_request.py::build_ob_search_request(application)`, which assembles the outbound payload (catalog § 6) from `field_values` + application data; it does not itself validate. Calling `PricingClient.get_priced_products` (CQ-009) with that payload raises `PricingValidationError(missing_fields: list[str])` (owned by CQ-009, defined in `app.integrations.common.errors`, subclassing CQ-004's `IntegrationError`/`AppError`) when required OB fields are missing, naming every missing field at once. Every route that prices (scenario create, products, autoquote) lets this propagate to CQ-004's `AppError` handler, which returns **HTTP 422** with CQ-004's pinned error shape: `{"error": {"code": "PRICING_VALIDATION_ERROR", "message": "Cannot price: missing Occupancy", "details": {"missing_fields": ["Occupancy", ...]}}}` — `message` uses the first missing field, matching system-design's exact wording. This is what the Temporal pipeline (CQ-011) surfaces on the application as Needs Attention (persona 7, Aisha Coleman).

**Default scenario sets** (`create_default_scenarios`, per `system-design.md` § LO Console → Quote Builder):

- *Investment (LTR/STR):* Group A prices at assumed DSCR bucket `ONE_TO_1_25` (DSCR=1.00 sent to OB) → Par + Buydown. Compute actual DSCR/bucket. If actual bucket == `ONE_TO_1_25`, stop — Group A's cards are returned once, flagged `collapsed: true` with the note "same pricing tier as the 1.00 assumption". Otherwise run Group B at the actual bucket → Par + Buydown, `collapsed: false`.
- *Primary:* Group A at the LO's chosen down payment → Par + Buydown. If chosen down payment < 20%, Group B at exactly 20% down (removes MI, LTV=80) → Par only. If chosen down payment ≥ 20%, no Group B (MI already absent).

**Save & AutoQuote** (`select_par_and_buydown(rows: list[PricedProductRow])`): best par = row with `is_par_rate=True`, tie-break by minimum `abs(discount_points_pct)` then lowest `note_rate` then `investor_name` (deterministic). Best buydown = lowest `note_rate` among rows with `0 < discount_points_pct <= 1.00`; `None` if no row qualifies. Persists both as `quotes` rows labelled `"Par"` / `"Buydown"`.

**DSCR two-pass loop** (`run_two_pass_dscr`, used by both `create_scenario` for investment strategies and `create_default_scenarios` Group B): pass 1 prices at the caller-supplied assumed bucket (default `ONE_TO_1_25`), computes actual DSCR/bucket via CQ-008's `bucket_for_dscr`. If actual bucket differs, pass 2 re-prices at the actual bucket. Max 2 passes. If pass 2's actual bucket differs again (flip-flop), keep the **lower-DSCR** result and write a `flags` row via CQ-012's `write_flag` helper (`tab=ApplicationTab.pricing`, `field_key="dscr_ratio"`, `rule="dscr_bucket_unstable"`, `severity=FlagSeverity.warning`) so the LO sees it — **not** `severity="info"`: per CQ-007, `info` never produces a `flags` row (it is reserved for silent auto-fixes), so a bucket-flip that must be visible on the Pricing tab has to be `warning` (non-blocking, but shown as a flag count). Returns `TwoPassDscrResult {computation, passes: int, bucket_flipped: bool}`.

**Auth (Decision — CQ-014 not built yet).** All routes depend on `deps.get_current_lo_stub()`, which returns a fixed dev LO id (env `DEV_LO_ID`, seeded in CQ-010) and does no real authentication. CQ-014 replaces this dependency's implementation only; route signatures and tests must not change.

**Performance.** `/quotes/preview` never calls a mock adapter (note rate + points come from the request body, already chosen or previously fetched) — it is `compute_quote` plus HTTP overhead only.

## Out of scope

- The `quote_engine` math itself — CQ-008 (imported, not reimplemented).
- Mock adapter implementations, `provider_*` tables, forced-failure toggles — CQ-009.
- Temporal workflow/activities that call this service (import, verify, validate, draft quote set stages) — CQ-011.
- Verification flags unrelated to pricing (phone, housing history, DTI, asset sufficiency) — CQ-012.
- Real staff authentication — CQ-014 (stub only, see Decision).
- Send tab, letter PDF, borrower report rendering — CQ-019/CQ-020/CQ-021/CQ-022.
- Quote Builder and Pricing Panel frontend UI — CQ-017/CQ-018.
- Generic field-value override/revert for non-pricing tabs (borrower, housing, credit) — owned by the applications feature, not this item.

## References

- `docs/design/system-design.md` §§ Automation-first input model (pipeline stages, "Cannot price" message), LO Console → Pricing panel & Quote Builder (default scenario sets, Save & AutoQuote), Calculation engine → DSCR pricing loop, Data model (`field_values`, `scenarios`, `quotes`, `flags`).
- `docs/design/data-field-catalog.md` §§ 6 (OB outbound/inbound payload + required-field rejection), 7 (enrichment sources/formulas), overrides O9, O11.
- `docs/backlog/CQ-008-quote-engine/spec.md` — `compute_quote`, `bucket_for_dscr`, `ScenarioInputs`/`QuoteComputation` contracts consumed here.

## Acceptance criteria

- [ ] AC1 — Roadmap exit: API tests pass and `/quotes/preview` responds in under 300 ms (engine only, no adapter latency). `pytest backend/app/features/pricing/scenarios/tests/test_quotes_preview_perf.py`.
- [ ] AC2 — `enrich_pricing_fields` writes `field_values` rows with the correct `source` for tax/insurance/LTR-rent/STR-revenue/HOA and skips fields already overridden. `test_enrichment.py`.
- [ ] AC3 — `PATCH .../field-values/{field_key}` sets `overridden_by`/`overridden_at`; `POST .../revert` restores the pre-override value and clears them. `test_field_value_override.py`.
- [ ] AC4 — Missing a required OB field returns HTTP 422 with body `{"error": {"code": "PRICING_VALIDATION_ERROR", "message": "Cannot price: missing Occupancy", "details": {"missing_fields": [...]}}}` (and equivalent for other fields). `test_ob_validation.py`.
- [ ] AC5 — Investment default scenario set produces the collapsed Group A only when actual DSCR bucket matches the 1.00 assumption, and two groups otherwise. `test_default_scenarios_investment.py`.
- [ ] AC6 — Primary default scenario set produces one group when chosen down payment ≥ 20%, two groups (second = Par only at 20%) when < 20%. `test_default_scenarios_primary.py`.
- [ ] AC7 — `select_par_and_buydown` picks the correct par (closest to 0 points) and buydown (lowest rate, ≤ 1.00 point) from a fixture rate sheet, and returns `None` buydown when no row qualifies. `test_autoquote_selection.py`.
- [ ] AC8 — `run_two_pass_dscr` re-prices exactly once when the bucket flips, stops at 2 passes, and sets `bucket_flipped=True` plus a `flags` row when it still disagrees after pass 2. `test_dscr_two_pass_loop.py`.
- [ ] AC9 — `GET /scenarios/{id}/products` returns 8–15 rows shaped per the catalog's inbound fields. `test_products_grid.py`.
- [ ] AC10 — `POST /scenarios/{id}/quotes` (manual pick) persists a `quotes` row with `computed` equal to `compute_quote` run on that scenario's inputs with the picked row's rate/points. `test_manual_quote.py`.
- [ ] AC11 — All routes are reachable without credentials (stub dependency) and raise CQ-004's `AuthenticationError` (401, code `AUTHENTICATION_ERROR`) only if `DEV_LO_ID` is unset. `test_auth_stub.py`.
- [ ] AC12 — `ruff check` and `mypy` clean on `backend/app/features/pricing/enrichment/` and `backend/app/features/pricing/scenarios/`.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Perf + API | `pytest backend/app/features/pricing/scenarios/tests/test_quotes_preview_perf.py` |
| AC2 | Unit | `pytest backend/app/features/pricing/enrichment/tests/test_enrichment.py` |
| AC3 | API | `pytest backend/app/features/pricing/enrichment/tests/test_field_value_override.py` |
| AC4 | API | `pytest backend/app/features/pricing/scenarios/tests/test_ob_validation.py` |
| AC5 | Unit | `pytest backend/app/features/pricing/scenarios/tests/test_default_scenarios_investment.py` |
| AC6 | Unit | `pytest backend/app/features/pricing/scenarios/tests/test_default_scenarios_primary.py` |
| AC7 | Unit | `pytest backend/app/features/pricing/scenarios/tests/test_autoquote_selection.py` |
| AC8 | Unit | `pytest backend/app/features/pricing/scenarios/tests/test_dscr_two_pass_loop.py` |
| AC9 | API | `pytest backend/app/features/pricing/scenarios/tests/test_products_grid.py` |
| AC10 | API | `pytest backend/app/features/pricing/scenarios/tests/test_manual_quote.py` |
| AC11 | API | `pytest backend/app/features/pricing/scenarios/tests/test_auth_stub.py` |
| AC12 | Static | `ruff check backend/app/features/pricing/enrichment/ backend/app/features/pricing/scenarios/`, `mypy` same paths |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Decision: auth stub (`get_current_lo_stub`, env `DEV_LO_ID`) — swap-in point for CQ-014, logged above.
- Decision: default DSCR assumption bucket is `ONE_TO_1_25` (i.e. DSCR = 1.00), matching system-design's "assumed DSCR 1.00".
- Decision: primary's "next down-payment step that removes MI" is a flat 20% (LTV=80), not a stepped ladder — the design text says "(or 20%)", so this is a direct reading, not a guess.
- Uses CQ-009's `PricingClient` Protocol and `PricingValidationError` (from `app.integrations.common.errors`); if CQ-009's module path ever changes, update the import in the route/service layer only, not the error name.
- Uses CQ-007's `field_values`, `scenarios`, `quotes`, `flags` tables; do not add new tables here — if a gap appears, note it in `plan.md` under "Decisions & questions" and check with CQ-007's owner before altering its migration.
