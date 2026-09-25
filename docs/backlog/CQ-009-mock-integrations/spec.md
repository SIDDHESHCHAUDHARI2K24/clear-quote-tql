# CQ-009 Mock integrations

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-007 |
| Kaneo task | CQ-009 in Kaneo (task id `kj6ktr2wmayhugqzjv70882k`) |
| Branch | `cq-009-mock-integrations` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

The pipeline, pricing service and console can call Encompass, Optimal Blue, RentCast, AirDNA and the rest through one stable interface per provider, get realistic latency and demo-able failures, and never touch a real third-party API. When this is done, every later item codes against a `Protocol`, not a live vendor SDK.

## Scope

9 adapter `Protocol`s (LOS, Pricing, Rent, STR, Tax, Insurance, Credit, PropertySearch, CRM) with one `Mock` implementation each, reading from the `provider_*`/`crm_events` tables CQ-007 created; shared latency simulation (200–1,200 ms); a per-adapter failure toggle; a call log for the CQ-029 Integration panel; the `PricingClient` rate-sheet selection algorithm and its required-field validation.

## Out of scope

- The `provider_*` table schemas themselves (CQ-007) and the persona/seed rows loaded into them (CQ-010).
- `quote_engine` money math — mocks return raw provider-shaped data; discount points formatting beyond what OB itself returns is the engine's job (CQ-008).
- Calling these adapters from the Temporal pipeline (CQ-011) or the pricing service (CQ-013).
- The Integration panel UI itself (CQ-029) — this item only guarantees the `integration_calls` rows it reads.

## References

- `docs/design/system-design.md` — "Emulated integrations", "Repo layout".
- `docs/design/data-field-catalog.md` — section 6 (OB request/response JSON), section 7 (third-party enrichment), section 11 (property match), section 12 (CRM).
- `docs/backlog/CQ-007-data-model/spec.md` — `provider_*`, `crm_events`, `integration_calls` table shapes.

## Module layout

```
backend/app/integrations/
  common/    errors.py  latency.py  failure_toggle.py  logging.py  models.py (IntegrationCall)  tests/
  los/       protocol.py  schemas.py  mock.py  tests/
  pricing/   protocol.py  schemas.py  mock.py  tests/
  rent/      protocol.py  schemas.py  mock.py  tests/
  str/       protocol.py  schemas.py  mock.py  tests/
  tax/       protocol.py  schemas.py  mock.py  tests/
  insurance/ protocol.py  schemas.py  mock.py  tests/
  credit/    protocol.py  schemas.py  mock.py  tests/
  property_search/  protocol.py  schemas.py  mock.py  tests/
  crm/       protocol.py  schemas.py  mock.py  tests/
```

Every `Mock*` class: (1) awaits `common.latency.simulate_latency(adapter)`, (2) checks `common.failure_toggle.is_forced_to_fail(adapter)` and raises `ProviderUnavailableError(adapter)` if set, (3) does its lookup, (4) calls `common.logging.record_call(...)` on the way out (success or failure) before returning/raising.

## Shared contracts (`integrations/common/`)

**Errors** (`errors.py`). All inherit CQ-004's `app.core.errors.IntegrationError` (which itself subclasses `AppError`), not bare `Exception`, so every integration failure flows through `register_exception_handlers` and comes back in CQ-004's pinned `{"error": {"code","message","details"}}` shape without each route needing its own `except` block:

| Error | Raised by | Fields | `status_code` | `code` | `details` |
| --- | --- | --- | --- | --- | --- |
| `ProviderUnavailableError` | any adapter, on forced failure or simulated timeout | `adapter: str` | 502 (inherited) | `PROVIDER_UNAVAILABLE` | `{"adapter": adapter}` |
| `PricingValidationError` | `PricingClient` | `missing_fields: list[str]` | **422** (overridden — a client-input problem, not a provider outage) | `PRICING_VALIDATION_ERROR` | `{"missing_fields": missing_fields}`; `message` = `f"Cannot price: missing {missing_fields[0]}"` (system-design's exact wording) |
| `LoanNotFoundError` | `LosClient` | `loan_number: str` | 502 (inherited) | `LOAN_NOT_FOUND` | `{"loan_number": loan_number}` |
| `RentDataNotFoundError` | `RentClient` | `zip_code: str` | 502 (inherited) | `RENT_DATA_NOT_FOUND` | `{"zip_code": zip_code}` |
| `StrDataNotFoundError` | `StrClient` | `zip_code: str` | 502 (inherited) | `STR_DATA_NOT_FOUND` | `{"zip_code": zip_code}` |
| `TaxRateNotFoundError` | `TaxClient` | `state: str`, `county: str` | 502 (inherited) | `TAX_RATE_NOT_FOUND` | `{"state": state, "county": county}` |
| `CreditPullFailedError` | `CreditClient` | `loan_number: str`, `pull_type: CreditPullType` | 502 (inherited) | `CREDIT_PULL_FAILED` | `{"loan_number": loan_number, "pull_type": pull_type}` |

**Latency** (`latency.py`): `async def simulate_latency(adapter: str) -> int` sleeps `random.uniform(min_ms, max_ms) / 1000` and returns the ms slept. Settings (pydantic-settings, from CQ-004's `Settings`): `integration_latency_min_ms: int = 200`, `integration_latency_max_ms: int = 1200`, `integration_latency_enabled: bool = True`. Env var `INTEGRATION_LATENCY_ENABLED=false` disables sleeping entirely (used in `conftest.py` for all non-latency-specific tests, so the suite stays fast).

**Failure toggle** (`failure_toggle.py`) — **Decision: stored in Valkey**, not the `settings` table, because CQ-029's Integration panel needs to flip it instantly without a request touching Postgres, and it should reset on `make demo-reset` without a migration: key `integration:fail:{adapter}` (string `"1"`/`"0"`, no TTL). `async def is_forced_to_fail(adapter: str) -> bool`; `async def set_forced_failure(adapter: str, enabled: bool) -> None`. Checked *after* `simulate_latency` so a forced failure still shows the loading state before erroring, matching "the error and retry states are real in the demo."

**Call log** (`logging.py`, `models.py`): `async def record_call(session: AsyncSession, adapter: str, request_summary: dict, success: bool, latency_ms: int, *, error_code: str | None = None, application_id: uuid.UUID | None = None, audit_sessionmaker: async_sessionmaker[AsyncSession] | None = None) -> None` inserts one `integration_calls` row (schema in CQ-007). **Decision (revised after review — post-dev.md finding #1):** `session` is the caller's session, used only to derive the audit write's own `AsyncEngine` (via `session.bind`, resolving through an `AsyncConnection` if the caller is bound to one, e.g. a test's `db_session`); `record_call` opens a *separate*, short-lived `AsyncSession` from that engine, inserts, and commits independently, so the audit row (a) survives a caller rollback (the failure path CQ-029's panel most needs) and (b) never commits the caller's other pending work. `audit_sessionmaker` is an injectable override for tests/callers that want to pin one explicitly; default derives one per call. No Valkey cache — CQ-029 reads the latest row per adapter with SQL. Every `Mock*.__init__(self, session: AsyncSession)` still takes the caller's session for its own provider-table reads (Protocols only constrain the async business methods, not `__init__`).

## Protocols, methods and DTOs

All methods `async`. DTOs are Pydantic v2 models in each adapter's `schemas.py`.

| Adapter | Protocol / module | Method | Request DTO | Response DTO |
| --- | --- | --- | --- | --- |
| Encompass | `LosClient` (`los/protocol.py`) | `async def get_loan_file(self, loan_number: str) -> LoanFileDTO` | — | `LoanFileDTO` — full 1003 payload, field names match catalog §1/§2/§4/§5 (borrower/co-borrower profile, housing, property, loan structure) |
| Optimal Blue | `PricingClient` (`pricing/protocol.py`) | `async def get_priced_products(self, request: PricingRequestDTO) -> list[PricedProductDTO]` | `PricingRequestDTO` — mirrors catalog §6 outbound JSON | `PricedProductDTO` — mirrors catalog §6 inbound fields: `investor_name`, `product_name`, `lock_period_days`, `note_rate`, `price_pct`, `discount_points_pct`, `discount_points_amount`, `is_par_rate`, `is_buydown_rate`, `piti_ob_estimate` (`None` — "the engine recomputes it") |
| RentCast | `RentClient` (`rent/protocol.py`) | `async def get_market_rent(self, zip_code: str, beds: int) -> MarketRentDTO` | — | `MarketRentDTO(market_rent, rent_low, rent_high, comps_count, as_of)` |
| AirDNA | `StrClient` (`str/protocol.py`) | `async def get_str_revenue(self, zip_code: str, beds: int) -> StrRevenueDTO` | — | `StrRevenueDTO(annual_revenue, occupancy_pct, adr, comps_count, as_of)` |
| SmartAsset/county | `TaxClient` (`tax/protocol.py`) | `async def get_tax_rate(self, state: str, county: str) -> TaxRateDTO` | — | `TaxRateDTO(annual_rate_pct, source_name, as_of)` |
| Steadily | `InsuranceClient` (`insurance/protocol.py`) | `async def get_insurance_estimate(self, state: str, purchase_price: Decimal) -> InsuranceEstimateDTO` | — | `InsuranceEstimateDTO(annual_premium, annual_rate_pct, source_name)` — always resolves (falls back to the 0.50% default factor if `state` has no row), never raises "not found" |
| Credit bureau | `CreditClient` (`credit/protocol.py`) | `async def pull_credit(self, loan_number: str, pull_type: CreditPullType) -> CreditReportDTO` | — | `CreditReportDTO(pull_type, experian_score, equifax_score, transunion_score, middle_score, tradelines)` — soft pull populates `experian_score` only (per catalog: "Soft pull only pulls Experian") |
| Property search | `PropertySearchClient` (`property_search/protocol.py`) | `async def search_matches(self, request: PropertySearchRequestDTO) -> list[PropertyMatchDTO]` | `PropertySearchRequestDTO(approved_purchase_price, buy_box_states, buy_box_metros, strategy)` | `PropertyMatchDTO(matched_property_id, address, city, state, zip, bed_bath_sqft, deal_grade, deal_ranking_score, tagline, image_url)` — empty list is a valid result, not an error |
| CRM | `CrmClient` (`crm/protocol.py`) | `async def log_event(self, contact_id: str, event_type: str, payload: dict) -> CrmEventDTO` | — | `CrmEventDTO(contact_id, event_type, at)` |

## OB required fields (`PricingRequestDTO`)

`MockPricingClient.get_priced_products` validates presence (not `None`/empty) before querying the rate sheet, and names every missing field at once in `PricingValidationError.missing_fields`:

Always required: `LoanPosition`, `LoanType`, `LoanPurpose`, `BaseLoanAmount`, `TotalLoanAmount`, `PurchasePrice`, `AppraisedValue`, `LTV`, `CLTV`, `HCLTV`, `RepresentativeFICO`, `Occupancy`, `PropertyType`, `NumberOfUnits`, `State`, `County`, `ZipCode`, `AmortizationType`, `AmortizationTerm`, `PrepaymentPenalty`, `IncomeVerificationType`, `DesiredLockDays`.

Conditionally required (**Decision**, not explicit in the catalog but implied by "DSCR is the assumed or computed value" and "ShortTermRental" only appearing on investment payloads): `DSCR` and `ShortTermRental` are required when `Occupancy == "InvestmentProperty"`; omitted (not validated) when `Occupancy == "PrimaryResidence"`. This is the exact path persona 7 (Aisha Coleman) hits: her LOS record has `Occupancy` empty, so `PricingValidationError(missing_fields=["Occupancy", ...])` is raised — see CQ-012's spec for how the pipeline turns that into the application's `NeedsAttention` flag; this item only guarantees the error is raised and named correctly.

## `PricingClient` rate-sheet algorithm

1. Validate required fields (above); raise `PricingValidationError` if any are missing.
2. `simulate_latency("pricing")`; raise `ProviderUnavailableError("pricing")` if the failure toggle is set.
3. Pick `program`: `dscr` if `Occupancy == "InvestmentProperty"` else `conventional`.
4. Compute `dscr_bucket` from `request.DSCR` using CQ-008's `bucket_for_dscr`/`DSCRBucket` names (`BELOW_1_00`, `ONE_TO_1_25`, `GE_1_25`) when `program == "dscr"`.
5. Query `provider_rate_sheet` where `active = true` and: `program` matches; `request.RepresentativeFICO >= min_fico`; `request.LTV <= max_ltv`; `dscr_bucket IS NULL OR dscr_bucket = <computed bucket>`; `ppp_years IS NULL OR ppp_years = <years parsed from request.PrepaymentPenalty>`; `NOT str_only OR request.ShortTermRental == "Yes"`; `lead_source IS NULL OR lead_source = request.LeadSource`.
6. For each matching row: `note_rate = base_rate + (fico_adjustment_bps + ltv_adjustment_bps) / 10000`; `price_pct = base_price`; `discount_points_pct = round((100 - price_pct) / 100, 5)`; `discount_points_amount = request.TotalLoanAmount * discount_points_pct`.
7. Mark `is_par_rate = true` on the row whose `price_pct` is closest to `100.000`; mark `is_buydown_rate = true` on the row with the next-lower `note_rate` than the par row whose points cost is between 0.75 and 1.00 (per catalog "bought with ~0.75%–1.00% points").
8. Sort ascending by `note_rate`; return the list. The seeded rate sheet (CQ-010) provides 8–15 active rows per program/bucket combination so a realistic query returns a multi-row grid.
9. `record_call("pricing", ...)` regardless of outcome.

## Acceptance criteria

- [ ] AC1 — Contract tests per adapter pass; forcing failure on any of the 9 adapters returns `ProviderUnavailableError(adapter=<name>)`. *(roadmap exit check)*
- [ ] AC2 — All 9 Protocols and their `Mock*` implementations exist at the module paths above with the exact method signatures listed.
- [ ] AC3 — With `integration_latency_enabled=True` (default), 100 calls to any one mock take at least 200 ms and at most 1,200 ms each; with `INTEGRATION_LATENCY_ENABLED=false`, the same 100 calls complete in under 1 s total.
- [ ] AC4 — `set_forced_failure("rent", True)` in Valkey makes the next `RentClient.get_market_rent` call raise; `set_forced_failure("rent", False)` clears it; the toggle is per-adapter (forcing `rent` does not affect `tax`).
- [ ] AC5 — Every mock call (success or failure) writes exactly one `integration_calls` row with a correct `latency_ms` and `success` flag.
- [ ] AC6 — `PricingClient.get_priced_products` raises `PricingValidationError` naming every missing required field when called with an empty `Occupancy`, reproducing persona 7's exact failure mode.
- [ ] AC7 — Against the seeded DSCR rate sheet fixture, a fully valid investment request returns 8–15 rows sorted ascending by `note_rate`, with exactly one `is_par_rate = true` row.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Contract (parametrized over 9 adapters) | `pytest backend/app/integrations/common/tests/test_contract.py` |
| AC2 | Unit | `pytest backend/app/integrations/*/tests/test_mock.py` |
| AC3 | Timing | `pytest backend/app/integrations/common/tests/test_latency.py` |
| AC4 | Unit | `pytest backend/app/integrations/common/tests/test_failure_toggle.py` |
| AC5 | Integration (test DB) | `pytest backend/app/integrations/common/tests/test_logging.py` |
| AC6 | Unit | `pytest backend/app/integrations/pricing/tests/test_validation.py::test_missing_occupancy` |
| AC7 | Unit (fixture rate sheet) | `pytest backend/app/integrations/pricing/tests/test_rate_sheet.py` |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Decision: failure toggle lives in Valkey, not `settings` (rationale above) — CQ-029 should read/write it through `common.failure_toggle`, not a new mechanism.
- Decision: `integrations/common/errors.py`'s `IntegrationError` is CQ-004's `app.core.errors.IntegrationError` re-exported (not a second, same-named class) — every adapter error subclasses it so the AppError hierarchy stays one chain; `PricingValidationError` overrides `status_code` to 422 since it is a caller-input problem the LO can fix, not a 502 provider outage. CQ-011's non-retryable activity list and CQ-013's route-level catches both reference these exact names.
- Decision: conditional OB-required-fields (`DSCR`, `ShortTermRental` only on investment) — the catalog's JSON example is investment-only and doesn't state this explicitly; treat it as load-bearing since CQ-013's validation stage and persona 7 both depend on it.
- Decision: `is_par_rate`/`is_buydown_rate` are computed inside the mock (OB's own "Formula" column per the catalog), not by `quote_engine` — keeps the emulated-provider boundary honest while still respecting "money math lives only in quote_engine" for everything downstream of the raw rate/price.
- `PricingClient` reads `provider_rate_sheet`; the other 7 read-adapters each read their own single `provider_*` table (CQ-007). `CrmClient` only ever writes to `crm_events`.
