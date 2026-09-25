"""AC6: `MockPricingClient` names every missing required OB field at once.

`test_missing_occupancy` reproduces persona 7 (Aisha Coleman)'s exact
failure mode per spec.md: her LOS record has `Occupancy` empty.
"""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import PricingValidationError
from app.integrations.pricing.mock import MockPricingClient
from app.integrations.pricing.schemas import PricingRequestDTO


def _base_kwargs() -> dict[str, Any]:
    """Every always-required field except `Occupancy`, fully populated."""
    return dict(
        LoanPosition="First",
        LoanType="Conventional",
        LoanPurpose="Purchase",
        BaseLoanAmount=Decimal("225000.00"),
        TotalLoanAmount=Decimal("225000.00"),
        PurchasePrice=Decimal("300000.00"),
        AppraisedValue=Decimal("300000.00"),
        LTV=Decimal("75.00"),
        CLTV=Decimal("75.00"),
        HCLTV=Decimal("75.00"),
        RepresentativeFICO=781,
        PropertyType="SingleFamily",
        NumberOfUnits=1,
        State="NC",
        County="Buncombe",
        ZipCode="28803",
        AmortizationType="Fixed",
        AmortizationTerm=360,
        PrepaymentPenalty="None",
        IncomeVerificationType="Full Doc",
        DesiredLockDays=30,
    )


async def test_missing_occupancy(db_session: AsyncSession) -> None:
    request = PricingRequestDTO(Occupancy="", **_base_kwargs())

    with pytest.raises(PricingValidationError) as exc_info:
        await MockPricingClient(db_session).get_priced_products(request)

    assert "Occupancy" in exc_info.value.missing_fields
    assert exc_info.value.message == f"Cannot price: missing {exc_info.value.missing_fields[0]}"
    assert exc_info.value.code == "PRICING_VALIDATION_ERROR"
    assert exc_info.value.status_code == 422


async def test_missing_single_field_names_only_that_field(db_session: AsyncSession) -> None:
    kwargs = _base_kwargs()
    kwargs.pop("RepresentativeFICO")
    request = PricingRequestDTO(Occupancy="PrimaryResidence", **kwargs)

    with pytest.raises(PricingValidationError) as exc_info:
        await MockPricingClient(db_session).get_priced_products(request)

    assert exc_info.value.missing_fields == ["RepresentativeFICO"]


async def test_investment_occupancy_requires_dscr_and_short_term_rental(
    db_session: AsyncSession,
) -> None:
    request = PricingRequestDTO(Occupancy="InvestmentProperty", **_base_kwargs())

    with pytest.raises(PricingValidationError) as exc_info:
        await MockPricingClient(db_session).get_priced_products(request)

    assert exc_info.value.missing_fields == ["DSCR", "ShortTermRental"]


async def test_primary_occupancy_does_not_require_dscr_or_short_term_rental(
    db_session: AsyncSession,
) -> None:
    request = PricingRequestDTO(Occupancy="PrimaryResidence", **_base_kwargs())

    # No PricingValidationError -- an empty rate sheet just returns [].
    products = await MockPricingClient(db_session).get_priced_products(request)
    assert products == []
