"""Cost segregation formula — supplementary coverage.

The binding golden case (AC7, $342,000 / 100% bonus / 32%) lives in
`test_golden.py`. This file covers the sub-fields (land/building/accelerated
basis) and a no-bonus case.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.features.pricing.engine.quote_engine import cost_segregation

_CENT = Decimal("0.01")


def test_cost_segregation_sub_fields_342k_100_bonus() -> None:
    land, building, accelerated, deduction, savings = cost_segregation(
        purchase_price=Decimal("342000"),
        land_allocation_pct=Decimal("0.20"),
        accelerated_property_pct=Decimal("0.25"),
        bonus_depreciation_pct=Decimal("1.00"),
        investor_marginal_tax_rate=Decimal("0.32"),
    )

    assert land.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("68400.00")
    assert building.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("273600.00")
    assert accelerated.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("68400.00")
    assert deduction.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("75861.82")
    assert savings.quantize(_CENT, rounding=ROUND_HALF_UP) == Decimal("24275.78")


def test_cost_segregation_no_bonus_depreciation() -> None:
    # bonus% == 0: Ded_1 collapses to straight-line only, (B - A) / 27.5.
    _land, building, accelerated, deduction, savings = cost_segregation(
        purchase_price=Decimal("200000"),
        land_allocation_pct=Decimal("0.20"),
        accelerated_property_pct=Decimal("0.25"),
        bonus_depreciation_pct=Decimal("0"),
        investor_marginal_tax_rate=Decimal("0.24"),
    )

    assert building == Decimal("160000")
    assert accelerated == Decimal("40000")
    expected_deduction = (building - accelerated) / Decimal("27.5")
    assert deduction == expected_deduction
    assert savings.quantize(_CENT, rounding=ROUND_HALF_UP) == (
        expected_deduction * Decimal("0.24")
    ).quantize(_CENT, rounding=ROUND_HALF_UP)
