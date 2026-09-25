"""`build_ob_search_request`: assembles the mock Optimal Blue outbound
search payload (catalog § 6) from `applications` + `properties` +
`field_values`. Validation itself happens in CQ-009's `PricingClient` --
this module only assembles, never raises `PricingValidationError` (spec.md).

Every field that isn't yet known (e.g. `RepresentativeFICO` before a credit
pull has written `field_values`) is simply left `None`; `PricingRequestDTO`
allows `None` everywhere for exactly this reason.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.core.errors import NotFoundError
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyType
from app.features.applications.verification.models import FieldValue
from app.features.pricing.engine.quote_engine import loan_amount, ltv_pct
from app.integrations.pricing.schemas import PricingRequestDTO

_PERCENT = Decimal("0.01")
_DEFAULT_DOWN_PAYMENT_PRIMARY = Decimal("0.20")
_DEFAULT_DOWN_PAYMENT_INVESTMENT = Decimal("0.25")
_DEFAULT_INVESTMENT_PPP_YEARS = 5
_DEFAULT_ASSUMED_DSCR = Decimal("1.00")
_DEFAULT_LOCK_DAYS = 30

_PROPERTY_TYPE_OB_NAME = {
    PropertyType.SINGLE_FAMILY: "SingleFamily",
    PropertyType.TWO_TO_FOUR_UNIT: "TwoToFourUnit",
    PropertyType.CONDO: "Condo",
    # Not in the catalog's example list; closest attached-housing category.
    PropertyType.TOWNHOME: "Condo",
}


@dataclass(frozen=True)
class ObRequestOverrides:
    """Scenario-specific values known once the LO has priced a scenario;
    `None`/absent fields fall back to system-design's stated defaults so
    `validate_ob_required_fields` can call this before any scenario exists.
    """

    down_payment_pct: Decimal | None = None
    dscr: Decimal | None = None
    prepayment_penalty_years: int | None = None
    desired_lock_days: int = _DEFAULT_LOCK_DAYS


async def _field_value_decimal(
    db: AsyncSession, application_id: uuid.UUID, field_key: str
) -> Decimal | None:
    row = (
        await db.execute(
            select(FieldValue).where(
                FieldValue.application_id == application_id, FieldValue.field_key == field_key
            )
        )
    ).scalar_one_or_none()
    if row is None or row.value is None:
        return None
    return Decimal(str(row.value))


async def _field_value_int(
    db: AsyncSession, application_id: uuid.UUID, field_key: str
) -> int | None:
    value = await _field_value_decimal(db, application_id, field_key)
    return int(value) if value is not None else None


def _prepayment_penalty_string(years: int | None) -> str | None:
    if years is None:
        return None
    return "None" if years == 0 else f"{years} Years"


async def build_ob_search_request(
    db: AsyncSession,
    application_id: uuid.UUID,
    overrides: ObRequestOverrides | None = None,
) -> PricingRequestDTO:
    overrides = overrides or ObRequestOverrides()

    application = await db.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    property_ = (
        await db.execute(select(Property).where(Property.application_id == application_id))
    ).scalar_one_or_none()

    is_investment = application.occupancy is Occupancy.INVESTMENT
    is_str = is_investment and application.strategy is Strategy.STR

    down_payment_pct = overrides.down_payment_pct
    if down_payment_pct is None:
        down_payment_pct = (
            _DEFAULT_DOWN_PAYMENT_INVESTMENT if is_investment else _DEFAULT_DOWN_PAYMENT_PRIMARY
        )

    purchase_price = application.requested_price
    loan = loan_amount(purchase_price, down_payment_pct) if purchase_price is not None else None
    ltv = (ltv_pct(down_payment_pct) * Decimal("100")).quantize(_PERCENT, rounding=ROUND_HALF_UP)

    fico = await _field_value_int(db, application_id, "representative_fico")

    ppp_years = overrides.prepayment_penalty_years
    if ppp_years is None:
        ppp_years = _DEFAULT_INVESTMENT_PPP_YEARS if is_investment else 0

    dscr = None
    short_term_rental = None
    if is_investment:
        dscr = overrides.dscr if overrides.dscr is not None else _DEFAULT_ASSUMED_DSCR
        short_term_rental = "Yes" if is_str else "No"

    return PricingRequestDTO(
        LoanPosition="First",
        LoanType="Non-Conforming" if is_investment else "Conventional",
        LoanPurpose="Purchase",
        BaseLoanAmount=loan,
        TotalLoanAmount=loan,
        PurchasePrice=purchase_price,
        AppraisedValue=purchase_price,
        LTV=ltv,
        CLTV=ltv,
        HCLTV=ltv,
        RepresentativeFICO=fico,
        Occupancy="InvestmentProperty" if is_investment else "PrimaryResidence",
        PropertyType=(
            _PROPERTY_TYPE_OB_NAME.get(property_.property_type) if property_ is not None else None
        ),
        NumberOfUnits=property_.number_of_units if property_ is not None else None,
        State=(
            property_.state or (property_.buy_box_states[0] if property_.buy_box_states else None)
            if property_ is not None
            else None
        ),
        County=property_.county if property_ is not None else None,
        ZipCode=property_.zip if property_ is not None else None,
        AmortizationType="Fixed",
        AmortizationTerm=360,
        PrepaymentPenalty=_prepayment_penalty_string(ppp_years),
        IncomeVerificationType="Investor - DSCR" if is_investment else "Full Doc",
        DesiredLockDays=overrides.desired_lock_days,
        DSCR=dscr,
        ShortTermRental=short_term_rental,
    )
