"""Golden tests from spec.md / docs/design/system-design.md's reference sheets.

AC1: running this whole file (`pytest .../test_golden.py`) is the roadmap
exit criterion — every test below must pass to the cent.

AC2-AC9 are individually named per spec.md's acceptance criteria. AC4's PITIA
($1,820.87) is an independent reference value; AC5-AC9 share one $342,000 /
20%-down / 7.5% STR scenario (confirmed by cross-checking: $342,000 x 0.80 =
$273,600, whose P&I at 7.5% is exactly AC3's $1,913.05, and qualifying rent
$2,440 / total_monthly_payment $2,704.11 ties AC6-AC9 together). See plan.md
Decision 8.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.features.pricing.engine.quote_engine import (
    bucket_for_dscr,
    cap_rate_pct,
    compute_quote,
    cost_segregation,
    dscr_ratio,
    monthly_cashflow_incl_tax,
    principal_and_interest,
    str_annual_rent_target,
    underwritten_str_rent,
)
from app.features.pricing.engine.types import (
    ConfigSnapshot,
    DSCRBucket,
    ScenarioInputs,
    StrategyType,
)

_CENT = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def test_pi_225000_at_7_125() -> None:
    pi = principal_and_interest(Decimal("225000"), Decimal("0.07125"), 360)
    assert _round(pi) == Decimal("1515.87")


def test_pi_273600_at_7_500() -> None:
    pi = principal_and_interest(Decimal("273600"), Decimal("0.075"), 360)
    assert _round(pi) == Decimal("1913.05")


def test_str_annual_rent_target() -> None:
    target = str_annual_rent_target(Decimal("1820.87"))
    assert _round(target) == Decimal("27313.05")


def test_str_underwritten_rent() -> None:
    # $3,050 gross monthly == $36,600 gross annual.
    rent = underwritten_str_rent(Decimal("36600"), Decimal("0.20"))
    assert _round(rent) == Decimal("2440.00")


def test_dscr_ratio() -> None:
    dscr = dscr_ratio(Decimal("2440"), Decimal("2704.11"))
    assert _round(dscr) == Decimal("0.90")
    assert bucket_for_dscr(dscr) is DSCRBucket.BELOW_1_00


def test_cost_segregation_342k() -> None:
    _land, _building, _accelerated, _deduction, savings = cost_segregation(
        purchase_price=Decimal("342000"),
        land_allocation_pct=Decimal("0.20"),
        accelerated_property_pct=Decimal("0.25"),
        bonus_depreciation_pct=Decimal("1.00"),
        investor_marginal_tax_rate=Decimal("0.32"),
    )
    assert _round(savings) == Decimal("24275.78")


def test_cap_rate() -> None:
    rate = cap_rate_pct(Decimal("2440"), Decimal("342000"), Decimal("0.75"))
    assert _round(rate) == Decimal("6.42")


def test_cashflow_incl_tax_benefit() -> None:
    result = monthly_cashflow_incl_tax(Decimal("-264.11"), Decimal("24275.78"))
    assert _round(result) == Decimal("1758.87")


def _str_342k_scenario() -> tuple[ScenarioInputs, ConfigSnapshot]:
    """The shared $342,000 / 20%-down / 7.5% STR scenario behind AC6-AC9 and
    AC14: property_tax_annual_rate is solved so total_monthly_payment lands
    on the pinned $2,704.11 (P&I $1,913.05 + tax + $142.50 insurance + $0 HOA)."""
    config = ConfigSnapshot()
    purchase_price = Decimal("342000")
    down_payment_pct = Decimal("0.20")
    note_rate = Decimal("0.075")
    insurance_annual_rate = Decimal("0.005")

    loan = purchase_price * (Decimal("1") - down_payment_pct)
    pi = principal_and_interest(loan, note_rate, 360)
    monthly_insurance = purchase_price * insurance_annual_rate / Decimal("12")
    target_total_monthly_payment = Decimal("2704.11")
    monthly_tax_needed = target_total_monthly_payment - pi - monthly_insurance
    property_tax_annual_rate = monthly_tax_needed * Decimal("12") / purchase_price

    inputs = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=note_rate,
        strategy=StrategyType.STR,
        fico=740,
        property_tax_annual_rate=property_tax_annual_rate,
        insurance_annual_rate=insurance_annual_rate,
        str_gross_annual_revenue=Decimal("36600"),  # $3,050/mo gross
        bonus_depreciation_pct=Decimal("1.00"),
        investor_marginal_tax_rate=Decimal("0.32"),
    )
    return inputs, config


def test_full_scenario_matches_all_pinned_golden_values() -> None:
    """End-to-end `compute_quote` reproduces every pinned value for the shared
    $342,000 STR scenario in one pass (AC6-AC9 via the real orchestration
    path, not just the isolated formula functions above)."""
    inputs, config = _str_342k_scenario()
    quote = compute_quote(inputs, config)

    assert quote.monthly_pi == Decimal("1913.05")
    assert quote.total_monthly_payment == Decimal("2704.11")
    assert quote.underwritten_str_rent == Decimal("2440.00")
    assert quote.qualifying_rent == Decimal("2440.00")
    assert quote.dscr_ratio == Decimal("0.90")
    assert quote.dscr_bucket is DSCRBucket.BELOW_1_00
    assert quote.monthly_cashflow == Decimal("-264.11")
    assert quote.cap_rate_pct == Decimal("6.42")
    assert quote.year_one_tax_savings == Decimal("24275.78")
    assert quote.monthly_cashflow_incl_tax == Decimal("1758.87")

    # Primary-only field is untouched on an investment scenario's opposite
    # number: MI never applies to LTR/STR regardless of LTV.
    assert quote.monthly_mi is None


def test_rounding_full_precision_internal() -> None:
    """AC14: compute_quote must reproduce $24,275.78 (not $24,276 — the
    prose in system-design.md rounds $68,400 + $7,462 = $75,862 at each
    step). Proves the engine carries full Decimal precision through the
    whole chain and rounds exactly once at output."""
    inputs, config = _str_342k_scenario()
    quote = compute_quote(inputs, config)

    assert quote.year_one_tax_savings == Decimal("24275.78")
    assert quote.year_one_tax_savings != Decimal("24276.00")
    assert quote.year_one_tax_deduction == Decimal("75861.82")
    assert quote.year_one_tax_deduction != Decimal("75862.00")
