"""AC10 — MI matrix lookup and strategy gating."""

from decimal import Decimal

import pytest

from app.features.pricing.engine.mi_matrix import mi_factor
from app.features.pricing.engine.quote_engine import LtvOutOfRangeError, compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType


def _primary_inputs(*, down_payment_pct: Decimal, fico: int) -> ScenarioInputs:
    return ScenarioInputs(
        purchase_price=Decimal("300000"),
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0.07"),
        strategy=StrategyType.PRIMARY,
        fico=fico,
        property_tax_annual_rate=Decimal("0.01"),
        insurance_annual_rate=Decimal("0.005"),
    )


def test_mi_factor_ltv95_fico700() -> None:
    # ltv_pct is a 0-1 fraction (0.95 == 95% LTV), like every other *_pct field.
    config = ConfigSnapshot()
    factor = mi_factor(Decimal("0.95"), 700, config)
    assert factor == Decimal("0.0083")


def test_mi_ltv95_fico700_applies() -> None:
    # 5% down -> LTV 95%.
    inputs = _primary_inputs(down_payment_pct=Decimal("0.05"), fico=700)
    quote = compute_quote(inputs, ConfigSnapshot())

    assert quote.ltv_pct == Decimal("0.9500")
    assert quote.monthly_mi is not None
    assert quote.monthly_mi > Decimal("0")


def test_no_mi_at_80_ltv() -> None:
    # 20% down -> LTV 80% exactly, at or below the 80% threshold.
    inputs = _primary_inputs(down_payment_pct=Decimal("0.20"), fico=700)
    quote = compute_quote(inputs, ConfigSnapshot())

    assert quote.ltv_pct == Decimal("0.8000")
    assert quote.monthly_mi is None


def test_ltv_over_97_percent_on_primary_raises() -> None:
    # Conventional financing caps at 97% LTV (3% down); anything above must
    # not silently fall through as "no MI required".
    inputs = _primary_inputs(down_payment_pct=Decimal("0.02"), fico=700)  # LTV 98%
    with pytest.raises(LtvOutOfRangeError):
        compute_quote(inputs, ConfigSnapshot())


def test_ltv_at_97_percent_on_primary_does_not_raise() -> None:
    # 97% LTV is the conventional maximum, not out of range.
    inputs = _primary_inputs(down_payment_pct=Decimal("0.03"), fico=700)  # LTV 97%
    quote = compute_quote(inputs, ConfigSnapshot())
    assert quote.ltv_pct == Decimal("0.9700")
    assert quote.monthly_mi is not None


def test_ltv_over_97_percent_on_investment_does_not_raise() -> None:
    # The 97% cap is a PRIMARY/conventional-MI concept; LTR/STR are untouched.
    inputs = ScenarioInputs(
        purchase_price=Decimal("300000"),
        down_payment_pct=Decimal("0.02"),  # LTV 98%
        note_rate=Decimal("0.07"),
        strategy=StrategyType.LTR,
        fico=700,
        property_tax_annual_rate=Decimal("0.01"),
        insurance_annual_rate=Decimal("0.005"),
        market_rent_ltr=Decimal("2500"),
    )
    quote = compute_quote(inputs, ConfigSnapshot())
    assert quote.ltv_pct == Decimal("0.9800")
    assert quote.monthly_mi is None


def test_no_mi_on_investment() -> None:
    config = ConfigSnapshot()
    for strategy, kwargs in (
        (StrategyType.LTR, {"market_rent_ltr": Decimal("2500")}),
        (StrategyType.STR, {"str_gross_annual_revenue": Decimal("36000")}),
    ):
        inputs = ScenarioInputs(
            purchase_price=Decimal("300000"),
            down_payment_pct=Decimal("0.05"),  # LTV 95% — would trigger MI on a primary loan
            note_rate=Decimal("0.07"),
            strategy=strategy,
            fico=620,  # worst FICO band — would trigger the highest MI factor on primary
            property_tax_annual_rate=Decimal("0.01"),
            insurance_annual_rate=Decimal("0.005"),
            **kwargs,  # type: ignore[arg-type]
        )
        quote = compute_quote(inputs, config)
        assert quote.monthly_mi is None
