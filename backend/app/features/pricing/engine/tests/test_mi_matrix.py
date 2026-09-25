"""AC10 — MI matrix lookup and strategy gating."""

from decimal import Decimal

from app.features.pricing.engine.mi_matrix import mi_factor
from app.features.pricing.engine.quote_engine import compute_quote
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
    config = ConfigSnapshot()
    factor = mi_factor(Decimal("95"), 700, config)
    assert factor == Decimal("0.0083")


def test_mi_ltv95_fico700_applies() -> None:
    # 5% down -> LTV 95%.
    inputs = _primary_inputs(down_payment_pct=Decimal("0.05"), fico=700)
    quote = compute_quote(inputs, ConfigSnapshot())

    assert quote.ltv_pct == Decimal("95.00")
    assert quote.monthly_mi is not None
    assert quote.monthly_mi > Decimal("0")


def test_no_mi_at_80_ltv() -> None:
    # 20% down -> LTV 80% exactly, at or below the 80% threshold.
    inputs = _primary_inputs(down_payment_pct=Decimal("0.20"), fico=700)
    quote = compute_quote(inputs, ConfigSnapshot())

    assert quote.ltv_pct == Decimal("80.00")
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
