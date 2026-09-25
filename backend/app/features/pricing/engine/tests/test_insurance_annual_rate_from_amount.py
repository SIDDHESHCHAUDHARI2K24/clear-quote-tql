"""`insurance_annual_rate_from_amount` -- copied verbatim from CQ-017
(pricing panel), coordinated so both items' branches merge to a single
copy of this function (see quote_engine.py's "Insurance rate conversion
(shared with CQ-017)" block). CQ-023 (`features/matches/service.py`)
calls this instead of dividing `insurance.annual_premium / listing.
list_price` itself (AGENTS.md: money math lives only in `quote_engine`).
"""

from decimal import Decimal

import pytest

from app.features.pricing.engine.quote_engine import (
    NonPositivePriceError,
    insurance_annual_rate_from_amount,
)


def test_insurance_annual_rate_from_amount_divides_unrounded() -> None:
    # 1500 / 300000 = 0.005 exactly -- picked to double as an exactness check.
    rate = insurance_annual_rate_from_amount(Decimal("300000.00"), Decimal("1500.00"))
    assert rate == Decimal("0.005")


def test_insurance_annual_rate_from_amount_does_not_round() -> None:
    # 1000 / 300000 = 0.00333... -- a non-terminating fraction. A rounded
    # helper would truncate/round this; the real function must not.
    rate = insurance_annual_rate_from_amount(Decimal("300000.00"), Decimal("1000.00"))
    assert rate == Decimal("1000.00") / Decimal("300000.00")
    assert str(rate).startswith("0.00333333")


def test_insurance_annual_rate_from_amount_zero_price_raises() -> None:
    with pytest.raises(NonPositivePriceError):
        insurance_annual_rate_from_amount(Decimal("0"), Decimal("1500.00"))


def test_insurance_annual_rate_from_amount_negative_price_raises() -> None:
    with pytest.raises(NonPositivePriceError):
        insurance_annual_rate_from_amount(Decimal("-100000.00"), Decimal("1500.00"))


def test_insurance_annual_rate_from_amount_is_a_value_error() -> None:
    # NonPositivePriceError must remain catchable as a plain ValueError
    # (a Pydantic model_validator relies on this in CQ-017).
    with pytest.raises(ValueError):
        insurance_annual_rate_from_amount(Decimal("0"), Decimal("1500.00"))
