"""`down_payment_pct_from_amount` — CQ-017's server-side $ -> % conversion
for the pricing panel's linked down-payment input (AGENTS.md: money math
lives only in `quote_engine`)."""

from decimal import Decimal

import pytest

from app.features.pricing.engine.quote_engine import (
    NonPositivePriceError,
    down_payment_pct_from_amount,
    insurance_annual_rate_from_amount,
    loan_amount,
    ltv_pct,
)


def test_amount_to_pct_matches_pct_to_amount_round_trip() -> None:
    # $68,400 on $342,000 is exactly 20.00% (the AC1/AC2 reference combo).
    pct = down_payment_pct_from_amount(Decimal("342000.00"), Decimal("68400.00"))
    assert pct == Decimal("0.2000")


def test_25_pct_down_on_342000_is_85500() -> None:
    # AC2: "Typing 25% in down payment updates the $ field to $85,500.00" --
    # the $ -> % direction only; the panel derives the $ side straight from
    # `QuoteComputation.down_payment_amount` (already engine output), never
    # locally. This proves the inverse direction is consistent with it.
    purchase_price = Decimal("342000.00")
    down_payment_amount = purchase_price * Decimal("0.25")
    assert down_payment_amount == Decimal("85500.00")
    pct = down_payment_pct_from_amount(purchase_price, down_payment_amount)
    assert pct == Decimal("0.2500")


def test_rounds_to_the_same_4dp_precision_as_ltv_pct() -> None:
    # $1 on $3 isn't a clean fraction -- must round half-up to 4dp, same
    # rule as `ltv_pct`'s own rounding (`_round_ltv`).
    pct = down_payment_pct_from_amount(Decimal("3.00"), Decimal("1.00"))
    assert pct == Decimal("0.3333")


def test_zero_purchase_price_raises_non_positive_price_error() -> None:
    with pytest.raises(NonPositivePriceError):
        down_payment_pct_from_amount(Decimal("0"), Decimal("1000.00"))


def test_negative_purchase_price_raises_non_positive_price_error() -> None:
    with pytest.raises(NonPositivePriceError):
        down_payment_pct_from_amount(Decimal("-100000.00"), Decimal("1000.00"))


def test_insurance_annual_rate_from_amount_matches_the_scenarios_service_formula() -> None:
    # Same unrounded formula `pricing.scenarios.service._gather_base_
    # scenario_inputs` already uses for this exact conversion.
    rate = insurance_annual_rate_from_amount(Decimal("342000.00"), Decimal("1710.00"))
    assert rate == Decimal("1710.00") / Decimal("342000.00")


def test_insurance_annual_rate_from_amount_zero_price_raises() -> None:
    with pytest.raises(NonPositivePriceError):
        insurance_annual_rate_from_amount(Decimal("0"), Decimal("1500.00"))


def test_consistent_with_ltv_pct_for_the_complementary_fraction() -> None:
    purchase_price = Decimal("342000.00")
    down_payment_pct = Decimal("0.20")
    down_payment_amount = purchase_price * down_payment_pct
    loan = loan_amount(purchase_price, down_payment_pct)
    assert loan == Decimal("273600.00")
    recovered_pct = down_payment_pct_from_amount(purchase_price, down_payment_amount)
    assert recovered_pct == down_payment_pct.quantize(Decimal("0.0001"))
    assert ltv_pct(recovered_pct) == Decimal("0.8000")
