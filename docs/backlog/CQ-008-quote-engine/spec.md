# CQ-008 Quote engine

| Field | Value |
| --- | --- |
| Phase | P1 Data, engine, pipeline |
| Depends on | CQ-004 |
| Kaneo task | CQ-008 in Kaneo (task id `tfrltrv0ypddzlexi8k2jkx9`) |
| Branch | `cq-008-quote-engine` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

A single pure Python function turns a scenario's inputs into every money number Clear Quote shows (P&I, PITIA, cash to close, DSCR, cashflow, cap rate, cost segregation), so the LO preview, borrower report and PDFs are always the same numbers computed the same way.

## Scope

Pure `quote_engine` module: P&I, PITIA, MI matrix, cash to close, qualifying rent, DSCR + bucket classification, cashflow, cap rate, cost segregation, `ConfigSnapshot`. Decimal throughout, no I/O, no DB, no network.

**Module path (binding):** `backend/app/features/pricing/engine/` — import path `app.features.pricing.engine.quote_engine`.

```
backend/app/features/pricing/engine/
  __init__.py
  quote_engine.py     # compute_quote() + per-formula functions
  types.py             # ScenarioInputs, ConfigSnapshot, QuoteComputation, StrategyType, DSCRBucket
  mi_matrix.py         # MI_MATRIX table + mi_factor()
  tests/
    test_golden.py
    test_pi.py
    test_mi_matrix.py
    test_dscr_bucket.py
    test_cost_segregation.py
    test_cash_to_close.py
    test_config_snapshot.py
```

**Public API**

```python
def compute_quote(inputs: ScenarioInputs, config: ConfigSnapshot) -> QuoteComputation: ...
def bucket_for_dscr(dscr: Decimal) -> DSCRBucket: ...
def mi_factor(ltv_pct: Decimal, fico: int, config: ConfigSnapshot) -> Decimal | None: ...
```

`ScenarioInputs` (frozen Pydantic v2 model, all money/rate fields `Decimal`): `purchase_price, down_payment_pct, note_rate, term_months=360, strategy: StrategyType (PRIMARY|LTR|STR), fico, property_tax_annual_rate, insurance_annual_rate, hoa_monthly=0, discount_points_pct=0, seller_credits=0, market_rent_ltr: Decimal|None, str_gross_annual_revenue: Decimal|None, target_dscr: Decimal|None, bonus_depreciation_pct: Decimal|None, investor_marginal_tax_rate: Decimal|None`. `market_rent_ltr` required when `strategy==LTR`; `str_gross_annual_revenue` required when `strategy==STR`; both `None` for `PRIMARY`.

`QuoteComputation` (frozen, all currency fields `Decimal` rounded to cents, DSCR to 2dp, cap rate to 2dp of percent): `loan_amount, ltv_pct, monthly_pi, monthly_tax, monthly_insurance, monthly_mi, monthly_hoa, total_monthly_payment` (PITIA), `discount_points_amount, lender_fees, title_fees, prepaid_interest, prepaid_insurance, prepaid_taxes, total_prepaids, total_closing_costs, cash_to_close`, and investment-only (`None` on PRIMARY): `qualifying_rent, underwritten_str_rent, dscr_ratio, dscr_bucket, monthly_cashflow, annual_cashflow, break_even_rent_ltr, str_annual_rent_target, cap_rate_pct, land_value_allocation, depreciable_building_basis, accelerated_basis_amount, year_one_tax_deduction, year_one_tax_savings, monthly_cashflow_incl_tax`. Also carries `config_snapshot: ConfigSnapshot` (the exact config used).

`ConfigSnapshot` (frozen, defaults below; `scenarios.config_snapshot` stores one of these as JSON per CQ-007):

| Field | Default |
| --- | --- |
| `lender_processing_fee` | `995.00` |
| `lender_underwriting_fee` | `795.00` (sum = `1,790.00`) |
| `title_rate_pct` | `0.007` |
| `insurance_rate_pct` | `0.005` |
| `prepaid_interest_days` | `15` |
| `prepaid_insurance_months` | `14` |
| `prepaid_tax_months` | `3` |
| `str_expense_ratio` | `0.20` |
| `cap_rate_multiplier` | `0.75` |
| `land_allocation_pct` | `0.20` |
| `accelerated_property_pct` | `0.25` |
| `bonus_depreciation_pct` | `1.00` (current tax year; overridable per scenario) |
| `investor_marginal_tax_rate` | `0.32` |
| `target_dscr` | `1.00` |
| `reserves_months_primary` | `2` |
| `reserves_months_investment` | `6` |
| `mi_matrix` | see below |

**MI matrix (Decision — no source values given; realistic conventional annual-premium bands).** Annual MI rate applied to `loan_amount`, financed monthly as `loan_amount × factor / 12`. Only applies when `strategy==PRIMARY` and `ltv_pct > 80`.

| LTV band | FICO < 680 | 680–719 | 720–759 | ≥ 760 |
| --- | --- | --- | --- | --- |
| 80.01–85.00% | 0.58% | 0.42% | 0.31% | 0.19% |
| 85.01–90.00% | 0.86% | 0.62% | 0.44% | 0.30% |
| 90.01–95.00% | 1.13% | 0.83% | 0.59% | 0.39% |
| 95.01–97.00% | 1.86% | 1.35% | 0.96% | 0.63% |

Bands are inclusive of their upper bound. `mi_factor` returns `None` (no MI) when `ltv_pct <= 80` or `strategy != PRIMARY`.

**DSCR buckets (Decision, evidenced by persona 5 "DSCR > 1.25 bucket" and the catalog's "Targets ≥ 1.00 or ≥ 1.25"):** `BELOW_1_00` (< 1.00), `ONE_TO_1_25` (1.00 ≤ dscr < 1.25), `GE_1_25` (≥ 1.25). `bucket_for_dscr` classifies the **unrounded** DSCR value, not the 2dp display value.

**Formulas** (see `docs/design/system-design.md` § Calculation engine, `docs/design/data-field-catalog.md` §§ 7–9):

- `L = P × (1 − d)`; `r = note_rate / 12`; `n = term_months`; `P&I = L·r(1+r)^n / ((1+r)^n − 1)`.
- `PITIA = P&I + (P × property_tax_annual_rate)/12 + monthly_insurance + monthly_mi + hoa_monthly`, where `monthly_insurance = P × insurance_annual_rate / 12`.
- `CTC = down_payment + lender_fees + discount_points_pct × L + title_fees + total_prepaids − seller_credits` (negative `discount_points_pct` is a credit). `title_fees = P × title_rate_pct`. `total_prepaids = P&I/30 × prepaid_interest_days + monthly_insurance × prepaid_insurance_months + monthly_tax × prepaid_tax_months`.
- Qualifying rent: LTR = `market_rent_ltr`; STR = `underwritten_str_rent = str_gross_annual_revenue/12 × (1 − str_expense_ratio)`.
- `dscr_ratio = qualifying_rent / total_monthly_payment`; `monthly_cashflow = qualifying_rent − total_monthly_payment`; `annual_cashflow = monthly_cashflow × 12`.
- `break_even_rent_ltr = total_monthly_payment × target_dscr`; `str_annual_rent_target = total_monthly_payment × 12 / 0.80`.
- `cap_rate_pct = qualifying_rent × 12 × cap_rate_multiplier / purchase_price`.
- Cost seg: `B = land_allocation... ` — precisely `B = (1 − land_allocation_pct) × P` (depreciable building basis), `A = accelerated_property_pct × B`, `Ded_1 = A × bonus_depreciation_pct + (B − A) / 27.5`, `year_one_tax_savings = Ded_1 × investor_marginal_tax_rate`, `monthly_cashflow_incl_tax = monthly_cashflow + year_one_tax_savings / 12`.

**Rounding rule (Decision, pinned).** `compute_quote` performs the entire calculation chain in unrounded `Decimal` (Python's default 28-significant-digit context is sufficient — verified below); every downstream formula reads the *unrounded* upstream value, never a previously-rounded field. Rounding to `ROUND_HALF_UP` happens exactly once per field, only when populating `QuoteComputation`: currency fields to 2dp (cents), `dscr_ratio` to 2dp, `cap_rate_pct` to 2dp of percent. `system-design.md`'s prose ($75,862 → $24,276) rounds at each step; the binding golden value is **$24,275.78** (single rounding at the end) — engine must reproduce $24,275.78, not $24,276.

## Out of scope

- Calling `PricingClient`/OB, the DSCR two-pass re-pricing orchestration (assumed-vs-computed bucket comparison, re-request, flagging) — CQ-013. This item only exposes `bucket_for_dscr` for CQ-013 to compare against.
- Persisting `scenarios`/`quotes` rows, `field_values`, enrichment, API routes — CQ-013.
- Asset sufficiency check (`assets ≥ CTC + reserves`) — CQ-012 uses `reserves_months_primary`/`reserves_months_investment` from `ConfigSnapshot`; this item only carries the config values.
- Mock adapters and OB rate sheet — CQ-009.
- Seed data generation — CQ-010.

## References

- `docs/design/system-design.md` §§ Calculation engine (Payment, Cash to close, Investment, Cost segregation, Golden tests), Data model (`scenarios`, `quotes`, `settings`).
- `docs/design/data-field-catalog.md` §§ 7 (Third-party enrichment formulas), 8 (Fee engine & closing cost), 9 (Investment analysis & cost segregation); overrides O4 (cost-seg formula), O5 (cap rate formula), O8 (title 0.7%).

## Acceptance criteria

- [ ] AC1 — Roadmap exit: all golden tests below pass to the cent. `pytest backend/app/features/pricing/engine/tests/test_golden.py`.
- [ ] AC2 — `test_pi_225000_at_7_125` — $225,000 @ 7.125%, 30y → `$1,515.87`.
- [ ] AC3 — `test_pi_273600_at_7_500` — $273,600 @ 7.500%, 30y → `$1,913.05`.
- [ ] AC4 — `test_str_annual_rent_target` — PITIA $1,820.87 → `str_annual_rent_target = $27,313.05` (displays as $27,313/yr).
- [ ] AC5 — `test_str_underwritten_rent` — $3,050 gross monthly → `underwritten_str_rent = $2,440.00`.
- [ ] AC6 — `test_dscr_ratio` — $2,440 ÷ $2,704.11 → `dscr_ratio = 0.90`, `dscr_bucket = BELOW_1_00`.
- [ ] AC7 — `test_cost_segregation_342k` — $342,000, 100% bonus, 32% marginal rate → `year_one_tax_savings = $24,275.78`.
- [ ] AC8 — `test_cap_rate` — $2,440 rent, $342,000 price → `cap_rate_pct = 6.42`.
- [ ] AC9 — `test_cashflow_incl_tax_benefit` — cashflow −$264.11 + $24,275.78/12 → `monthly_cashflow_incl_tax = $1,758.87`.
- [ ] AC10 — MI matrix: `test_mi_ltv95_fico700_applies` (LTV 95%, FICO 700 → factor 0.83%, `monthly_mi > 0`), `test_no_mi_at_80_ltv` (LTV ≤ 80% → `monthly_mi is None`), `test_no_mi_on_investment` (strategy LTR/STR → `monthly_mi is None` regardless of LTV).
- [ ] AC11 — DSCR bucket boundaries: `test_dscr_bucket_boundaries` covers 0.99 → `BELOW_1_00`, 1.00 → `ONE_TO_1_25`, 1.24 → `ONE_TO_1_25`, 1.25 → `GE_1_25`.
- [ ] AC12 — `test_cash_to_close_with_credit` — negative `discount_points_pct` reduces CTC as a credit; `test_cash_to_close_formula` matches `CTC = D + F_lender + points×L + F_title + prepaids − credits` on a known input.
- [ ] AC13 — `test_config_snapshot_defaults` asserts every default in the table above; `test_config_snapshot_frozen` asserts `ConfigSnapshot` is immutable and a stored `QuoteComputation.config_snapshot` does not change when module-level defaults change later.
- [ ] AC14 — `test_rounding_full_precision_internal` asserts `compute_quote` reproduces $24,275.78 (not $24,276) for the cost-seg case, proving no intermediate rounding.
- [ ] AC15 — `ruff check` and `mypy` are clean on `backend/app/features/pricing/engine/`.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Unit (golden) | `pytest backend/app/features/pricing/engine/tests/test_golden.py` |
| AC2–AC9 | Unit (golden, named) | Same file, one test function per case (names above) |
| AC10 | Unit | `pytest backend/app/features/pricing/engine/tests/test_mi_matrix.py` |
| AC11 | Unit | `pytest backend/app/features/pricing/engine/tests/test_dscr_bucket.py` |
| AC12 | Unit | `pytest backend/app/features/pricing/engine/tests/test_cash_to_close.py` |
| AC13 | Unit | `pytest backend/app/features/pricing/engine/tests/test_config_snapshot.py` |
| AC14 | Unit | `pytest backend/app/features/pricing/engine/tests/test_golden.py::test_rounding_full_precision_internal` |
| AC15 | Static | `ruff check backend/app/features/pricing/engine/`, `mypy backend/app/features/pricing/engine/` |

## Notes for the agent

- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
- Decision: MI matrix values, DSCR bucket boundaries, `reserves_months_*`, and the down-payment-step rule are invented for realism (not sourced from the reference sheets) — logged above; if the human has real MGIC/Radian rate cards, swap the table without changing the function signature.
- Decision: use Python's default `Decimal` context (28 significant digits); do not narrow precision mid-calculation. Verified by hand for both P&I golden cases and the cost-seg case.
- `StrategyType` (`PRIMARY|LTR|STR`) is the engine's single occupancy/strategy field; CQ-007's `applications.occupancy` + `applications.strategy` columns map onto it — that mapping is CQ-013's job, not this item's.
- The two-pass DSCR re-pricing *loop* (calling OB twice) is explicitly CQ-013's scope; this item only provides the pure classification function it needs.
