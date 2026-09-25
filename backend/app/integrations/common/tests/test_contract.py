"""AC1: contract test, parametrized over all 9 adapters. Forcing failure on
any one of them raises `ProviderUnavailableError(adapter=<name>)`.

Every adapter's call reaches the failure-toggle check before touching the
database (pricing validates its own required fields first, per spec.md's
algorithm, so its case below uses a fully valid request), so none of these
cases need seeded provider rows.
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError
from app.integrations.common.failure_toggle import set_forced_failure
from app.integrations.credit.mock import MockCreditClient
from app.integrations.credit.models import CreditPullType
from app.integrations.crm.mock import MockCrmClient
from app.integrations.insurance.mock import MockInsuranceClient
from app.integrations.los.mock import MockLosClient
from app.integrations.pricing.mock import MockPricingClient
from app.integrations.pricing.schemas import PricingRequestDTO
from app.integrations.property_search.mock import MockPropertySearchClient
from app.integrations.property_search.schemas import MatchStrategy, PropertySearchRequestDTO
from app.integrations.rent.mock import MockRentClient
from app.integrations.str.mock import MockStrClient
from app.integrations.tax.mock import MockTaxClient


def _valid_pricing_request() -> PricingRequestDTO:
    """A fully valid *primary* request -- every always-required field set,
    no conditionally-required (investment-only) fields needed."""
    return PricingRequestDTO(
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
        Occupancy="PrimaryResidence",
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


ADAPTER_CALLS: dict[str, Callable[[AsyncSession], Awaitable[object]]] = {
    "los": lambda session: MockLosClient(session).get_loan_file("LN-CONTRACT-1"),
    "pricing": lambda session: MockPricingClient(session).get_priced_products(
        _valid_pricing_request()
    ),
    "rent": lambda session: MockRentClient(session).get_market_rent("28803", 3),
    "str": lambda session: MockStrClient(session).get_str_revenue("28803", 3),
    "tax": lambda session: MockTaxClient(session).get_tax_rate("NC", "Buncombe"),
    "insurance": lambda session: MockInsuranceClient(session).get_insurance_estimate(
        "NC", Decimal("300000.00")
    ),
    "credit": lambda session: MockCreditClient(session).pull_credit(
        "LN-CONTRACT-1", CreditPullType.SOFT_PULL
    ),
    "property_search": lambda session: MockPropertySearchClient(session).search_matches(
        PropertySearchRequestDTO(
            approved_purchase_price=Decimal("300000.00"),
            buy_box_states=["NC"],
            buy_box_metros=["Asheville"],
            strategy=MatchStrategy.LTR,
        )
    ),
    "crm": lambda session: MockCrmClient(session).log_event("contact-1", "quote_sent", {}),
}


@pytest.mark.parametrize("adapter", sorted(ADAPTER_CALLS))
async def test_forced_failure_raises_provider_unavailable(
    adapter: str, db_session: AsyncSession
) -> None:
    await set_forced_failure(adapter, True)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await ADAPTER_CALLS[adapter](db_session)

    assert exc_info.value.adapter == adapter
    assert exc_info.value.details == {"adapter": adapter}
    assert exc_info.value.code == "PROVIDER_UNAVAILABLE"
    assert exc_info.value.status_code == 502

    await set_forced_failure(adapter, False)
