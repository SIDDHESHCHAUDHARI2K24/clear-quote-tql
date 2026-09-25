"""Review finding 5 — ScenarioInputs cross-field validation.

`market_rent_ltr` is required (and only meaningful) when `strategy == LTR`;
`str_gross_annual_revenue` is required (and only meaningful) when
`strategy == STR`; both must be `None` for `PRIMARY`. Implemented as a
Pydantic `@model_validator(mode="after")` that raises `ValueError`
(`pydantic.ValidationError` is itself a `ValueError` subclass in v2).
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.features.pricing.engine.types import ScenarioInputs, StrategyType


def _scenario(
    *,
    strategy: StrategyType,
    market_rent_ltr: Decimal | None = None,
    str_gross_annual_revenue: Decimal | None = None,
) -> ScenarioInputs:
    return ScenarioInputs(
        purchase_price=Decimal("300000"),
        down_payment_pct=Decimal("0.20"),
        note_rate=Decimal("0.07"),
        strategy=strategy,
        fico=720,
        property_tax_annual_rate=Decimal("0.01"),
        insurance_annual_rate=Decimal("0.005"),
        market_rent_ltr=market_rent_ltr,
        str_gross_annual_revenue=str_gross_annual_revenue,
    )


def test_ltr_requires_market_rent() -> None:
    with pytest.raises(ValidationError, match="market_rent_ltr is required"):
        _scenario(strategy=StrategyType.LTR)


def test_ltr_forbids_str_revenue() -> None:
    with pytest.raises(ValidationError, match="str_gross_annual_revenue must be None"):
        _scenario(
            strategy=StrategyType.LTR,
            market_rent_ltr=Decimal("2500"),
            str_gross_annual_revenue=Decimal("36000"),
        )


def test_str_requires_gross_annual_revenue() -> None:
    with pytest.raises(ValidationError, match="str_gross_annual_revenue is required"):
        _scenario(strategy=StrategyType.STR)


def test_str_forbids_market_rent() -> None:
    with pytest.raises(ValidationError, match="market_rent_ltr must be None"):
        _scenario(
            strategy=StrategyType.STR,
            str_gross_annual_revenue=Decimal("36000"),
            market_rent_ltr=Decimal("2500"),
        )


def test_primary_forbids_market_rent() -> None:
    with pytest.raises(ValidationError, match="must be None when"):
        _scenario(strategy=StrategyType.PRIMARY, market_rent_ltr=Decimal("2500"))


def test_primary_forbids_str_revenue() -> None:
    with pytest.raises(ValidationError, match="must be None when"):
        _scenario(strategy=StrategyType.PRIMARY, str_gross_annual_revenue=Decimal("36000"))


def test_valid_ltr_constructs() -> None:
    inputs = _scenario(strategy=StrategyType.LTR, market_rent_ltr=Decimal("2500"))
    assert inputs.market_rent_ltr == Decimal("2500")


def test_valid_str_constructs() -> None:
    inputs = _scenario(strategy=StrategyType.STR, str_gross_annual_revenue=Decimal("36000"))
    assert inputs.str_gross_annual_revenue == Decimal("36000")


def test_valid_primary_constructs() -> None:
    inputs = _scenario(strategy=StrategyType.PRIMARY)
    assert inputs.market_rent_ltr is None
    assert inputs.str_gross_annual_revenue is None
