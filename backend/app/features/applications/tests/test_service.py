"""Integration tests for `import_from_los` against the real (test) database.

Builds its own minimum row graph (users -> clients -> applications ->
provider_los_records) rather than depending on `seed/` (CQ-010's seed
package is a separate consumer of this same function, not a test
dependency, per the pattern already used by
`applications/verification/tests/conftest.py`).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Occupancy, Strategy, UserRole
from app.features.applications.assets.models import Asset, Employment
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory
from app.features.applications.models import (
    Application,
    ApplicationParty,
    BusinessVesting,
    PartyRole,
)
from app.features.applications.service import ImportResult, import_from_los
from app.features.auth.models import User
from app.features.clients.models import Client
from app.integrations.common.errors import LoanNotFoundError
from app.integrations.los.models import ProviderLosRecord


async def _make_application(
    db_session: AsyncSession, *, loan_number: str, occupancy: Occupancy = Occupancy.INVESTMENT
) -> Application:
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
        password_hash="not-a-real-hash",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()

    client = Client(
        full_name="Test Client",
        email=f"client-{uuid.uuid4()}@clearquote-demo.test",
        assigned_lo_id=lo.id,
    )
    db_session.add(client)
    await db_session.flush()

    application = Application(
        client_id=client.id,
        lo_id=lo.id,
        occupancy=occupancy,
        strategy=Strategy.LTR if occupancy is Occupancy.INVESTMENT else None,
        requested_price=Decimal("300000.00"),
        los_loan_guid=loan_number,
    )
    db_session.add(application)
    await db_session.flush()
    return application


async def _seed_los_record(
    db_session: AsyncSession, loan_number: str, payload: dict
) -> ProviderLosRecord:
    record = ProviderLosRecord(loan_number=loan_number, payload=payload)
    db_session.add(record)
    await db_session.flush()
    return record


_FULL_PAYLOAD = {
    "borrower_first_name": "Tom",
    "borrower_last_name": "Brandt",
    "borrower_full_name": "Tom Brandt",
    "borrower_ssn": "123456789",
    "borrower_dob": "1980-01-01",
    "marital_status": "Married",
    "dependents_count": 2,
    "borrower_email": "tom.brandt@clearquote-demo.test",
    "borrower_cell_phone": "2165551234",
    "borrower_home_phone": None,
    "has_co_borrower": True,
    "no_co_applicant_check": False,
    "co_borrower_full_name": "Lisa Brandt",
    "co_borrower_ssn": "987654321",
    "business_vesting": "Personal Name",
    "current_street_address": "123 Lake Ave",
    "current_city": "Cleveland",
    "current_state": "OH",
    "current_zip": "44102",
    "current_housing_status": "Own",
    "current_residence_years": 2,
    "current_residence_months": 6,
    "loan_purpose": "Purchase",
    "occupancy_type": "Investment_Property",
    "investment_strategy": "Long_Term_Rental",
    "purchase_price": "250000.00",
    "employment": [
        {
            "employer_name": "Acme Corp",
            "monthly_income": "8000.00",
            "years_at_job": "5.0",
            "self_employed": False,
        }
    ],
    "liabilities": [
        {
            "creditor_name": "Chase",
            "account_type": "Credit Card",
            "monthly_payment": "150.00",
            "balance": "3000.00",
        }
    ],
    "assets": [
        {
            "account_type": "Checking",
            "institution": "Chase Bank",
            "verified_amount": "50000.00",
        }
    ],
}


async def test_import_from_los_writes_all_five_tables_and_advances_status(
    db_session: AsyncSession,
) -> None:
    loan_number = f"LOS-{uuid.uuid4().hex[:8]}"
    application = await _make_application(db_session, loan_number=loan_number)
    await _seed_los_record(db_session, loan_number, _FULL_PAYLOAD)

    result = await import_from_los(application.id, db_session)

    assert isinstance(result, ImportResult)
    assert result.parties_created == 2
    assert result.housing_rows_created == 1
    assert result.employment_rows_created == 1
    assert result.liabilities_created == 1
    assert result.assets_created == 1

    await db_session.refresh(application)
    assert application.status is ApplicationStatus.VERIFYING

    parties = (
        (
            await db_session.execute(
                select(ApplicationParty).where(ApplicationParty.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    by_role = {p.role: p for p in parties}
    assert by_role[PartyRole.BORROWER].first_name == "Tom"
    assert by_role[PartyRole.BORROWER].ssn_encrypted == "123456789"
    assert by_role[PartyRole.BORROWER].dob == date(1980, 1, 1)
    assert by_role[PartyRole.BORROWER].business_vesting is BusinessVesting.PERSONAL_NAME
    assert by_role[PartyRole.CO_BORROWER].first_name == "Lisa"
    assert by_role[PartyRole.CO_BORROWER].last_name == "Brandt"
    assert by_role[PartyRole.CO_BORROWER].ssn_encrypted == "987654321"

    housing = (
        (
            await db_session.execute(
                select(HousingHistory).where(HousingHistory.application_id == application.id)
            )
        )
        .scalars()
        .one()
    )
    assert housing.residence_years == 2
    assert housing.residence_months == 6

    employment_stmt = select(Employment).where(Employment.application_id == application.id)
    employment = (await db_session.execute(employment_stmt)).scalars().one()
    assert employment.monthly_income == Decimal("8000.00")

    liability_stmt = select(Liability).where(Liability.application_id == application.id)
    liability = (await db_session.execute(liability_stmt)).scalars().one()
    assert liability.monthly_payment == Decimal("150.00")

    asset = (
        (await db_session.execute(select(Asset).where(Asset.application_id == application.id)))
        .scalars()
        .one()
    )
    assert asset.verified_amount == Decimal("50000.00")


async def test_import_from_los_handles_missing_occupancy_type_without_error(
    db_session: AsyncSession,
) -> None:
    """Persona 7's exact defect: `occupancy_type` is null on the LOS record.
    `import_from_los` never reads `occupancy_type` (decision #2, plan.md --
    `applications.occupancy` is already set at intake) so this must not
    raise; the missing field only matters to CQ-013's later OB validation."""
    loan_number = f"LOS-{uuid.uuid4().hex[:8]}"
    application = await _make_application(db_session, loan_number=loan_number)
    payload = dict(_FULL_PAYLOAD)
    payload["occupancy_type"] = None
    payload["has_co_borrower"] = False
    await _seed_los_record(db_session, loan_number, payload)

    result = await import_from_los(application.id, db_session)

    assert result.parties_created == 1
    await db_session.refresh(application)
    assert application.status is ApplicationStatus.VERIFYING


async def test_import_from_los_no_prior_address_leaves_single_housing_row(
    db_session: AsyncSession,
) -> None:
    """Persona 8's exact defect: 14 months at the current address, no prior
    address on file -- `housing_history_24mo` (CQ-012) then fails against
    this single row's total."""
    loan_number = f"LOS-{uuid.uuid4().hex[:8]}"
    application = await _make_application(
        db_session, loan_number=loan_number, occupancy=Occupancy.PRIMARY
    )
    payload = dict(_FULL_PAYLOAD)
    payload["current_residence_years"] = 1
    payload["current_residence_months"] = 2
    payload["previous_street_address"] = None
    payload["has_co_borrower"] = False
    await _seed_los_record(db_session, loan_number, payload)

    result = await import_from_los(application.id, db_session)

    assert result.housing_rows_created == 1
    housing = (
        (
            await db_session.execute(
                select(HousingHistory).where(HousingHistory.application_id == application.id)
            )
        )
        .scalars()
        .one()
    )
    total_months = housing.residence_years * 12 + housing.residence_months
    assert total_months == 14


async def test_import_from_los_raises_when_loan_not_found(db_session: AsyncSession) -> None:
    application = await _make_application(db_session, loan_number="LOS-DOES-NOT-EXIST")

    with pytest.raises(LoanNotFoundError):
        await import_from_los(application.id, db_session)
