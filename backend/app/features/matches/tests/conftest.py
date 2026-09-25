"""Local fixtures for `matches/tests` -- own copy of `pricing/conftest.py`'s
`make_application`/`set_field_value` pattern (not an import: pytest's
conftest discovery only reaches up the directory tree, and `matches/tests`
is a sibling of `pricing/`, not nested under it -- same reasoning as
`portal/reports/tests/conftest.py`'s own docstring), extended with the
buy-box/`recommend_matches` fields this feature actually needs.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FieldSource, Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import User
from app.features.clients.models import Client
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(
        occupancy: Occupancy = Occupancy.INVESTMENT,
        strategy: Strategy | None = Strategy.LTR,
        requested_price: Decimal | None = Decimal("300000.00"),
        first_name: str = "Test",
        last_name: str = "Client",
        address_status: PropertyAddressStatus = PropertyAddressStatus.TBD,
        buy_box_states: list[str] | None = None,
        buy_box_metros: list[str] | None = None,
        recommend_matches: bool = True,
        property_type: PropertyType = PropertyType.SINGLE_FAMILY,
        state: str | None = "FL",
        county: str | None = "Polk",
        zip_code: str | None = "33896",
        city: str | None = "Davenport",
        lo: User | None = None,
    ) -> Application:
        if lo is None:
            lo = User(
                email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
                password_hash="not-a-real-hash",
                role=UserRole.LO,
                full_name="Jordan Blake",
                nmls="1933377",
                title="Loan Officer",
                phone="8135550100",
            )
            db_session.add(lo)
            await db_session.flush()

        client = Client(
            full_name=f"{first_name} {last_name}",
            email=f"{first_name.lower()}.{last_name.lower()}-{uuid.uuid4()}@example.com",
            assigned_lo_id=lo.id,
        )
        db_session.add(client)
        await db_session.flush()

        application = Application(
            client_id=client.id,
            lo_id=lo.id,
            occupancy=occupancy,
            strategy=strategy,
            requested_price=requested_price,
        )
        db_session.add(application)
        await db_session.flush()

        db_session.add(
            Property(
                application_id=application.id,
                address_status=address_status,
                street_address=None if address_status is PropertyAddressStatus.TBD else "1 Test St",
                city=city,
                state=state,
                zip=zip_code,
                county=county,
                property_type=property_type,
                number_of_units=1,
                buy_box_states=buy_box_states or [],
                buy_box_metros=buy_box_metros or [],
                recommend_matches=recommend_matches,
            )
        )
        await db_session.flush()
        return application

    return _make


@pytest_asyncio.fixture
async def set_field_value(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[FieldValue]]:
    async def _set(
        application_id: uuid.UUID, field_key: str, value: Decimal | str, source: str = "lo_entry"
    ) -> FieldValue:
        row = FieldValue(
            application_id=application_id,
            field_key=field_key,
            value=str(value) if isinstance(value, Decimal) else value,
            source=FieldSource(source),
        )
        db_session.add(row)
        await db_session.flush()
        return row

    return _set


def seed_dscr_rate_sheet(db_session: AsyncSession, dscr_bucket: str, par_rate: Decimal) -> None:
    """Own copy of `portal/reports/tests/conftest.py`'s helper of the same
    name -- a minimal DSCR curve at a single bucket, matching
    `pricing/scenarios/tests/test_default_scenarios_investment.py`'s own
    fixture shape."""
    offsets = [Decimal("-0.250"), Decimal("0.000"), Decimal("0.250")]
    for index, offset in enumerate(offsets):
        db_session.add(
            ProviderRateSheet(
                investor_name=f"Investor {dscr_bucket}-{index}",
                product_name="DSCR 30 Yr Fixed",
                program=RateSheetProgram.DSCR,
                base_rate=par_rate + offset,
                base_price=Decimal("100.000") - offset * Decimal("4"),
                min_fico=680,
                max_ltv=Decimal("80.00"),
                dscr_bucket=dscr_bucket,
                lock_days=30,
                active=True,
            )
        )


def seed_conventional_rate_sheet(db_session: AsyncSession) -> None:
    """Own copy of `portal/reports/tests/conftest.py`'s helper of the same
    name -- a minimal Conventional curve so `auto_price` has par + buydown
    candidates for a PRIMARY application."""
    for index, offset in enumerate([Decimal("-0.25"), Decimal("0.00"), Decimal("0.25")]):
        db_session.add(
            ProviderRateSheet(
                investor_name=f"Investor {index}",
                product_name="Conventional 30 Yr Fixed",
                program=RateSheetProgram.CONVENTIONAL,
                base_rate=Decimal("7.000") + offset,
                base_price=Decimal("100.000") - offset * Decimal("4"),
                min_fico=680,
                max_ltv=Decimal("97.00"),
                lock_days=30,
                active=True,
            )
        )
