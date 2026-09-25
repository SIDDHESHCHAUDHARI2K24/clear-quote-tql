from decimal import Decimal

from app.features.pricing.engine.borrower_ratios import (
    assets_sufficient,
    debt_to_income_ratio,
    required_funds_amount,
    reserves_required_amount,
)


def test_dti_ratio_rounds_to_4dp() -> None:
    assert debt_to_income_ratio(Decimal("300"), Decimal("1700"), Decimal("6000")) == Decimal(
        "0.3333"
    )


def test_dti_none_when_no_income() -> None:
    assert debt_to_income_ratio(Decimal("300"), Decimal("1700"), Decimal("0")) is None


def test_reserves_and_sufficiency() -> None:
    reserves = reserves_required_amount(6, Decimal("1523.456"))
    assert reserves == Decimal("9140.74")
    required = required_funds_amount(Decimal("80000.00"), reserves)
    assert required == Decimal("89140.74")
    assert assets_sufficient(Decimal("89140.74"), required) is True
    assert assets_sufficient(Decimal("89140.73"), required) is False
