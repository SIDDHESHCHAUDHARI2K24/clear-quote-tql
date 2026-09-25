"""Local fixtures shared by `pricing/enrichment/tests` and
`pricing/scenarios/tests`.

`make_application` builds the minimum row graph (`users` -> `clients` ->
`applications` [-> `properties`]) every route/service test needs, following
`applications/verification/tests/conftest.py`'s established pattern rather
than depending on CQ-010's seed data.
"""

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


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(
        occupancy: Occupancy = Occupancy.PRIMARY,
        strategy: Strategy | None = None,
        requested_price: Decimal | None = Decimal("300000.00"),
        with_property: bool = True,
        state: str | None = "NC",
        county: str | None = "Buncombe",
        zip_code: str | None = "28803",
        property_type: PropertyType = PropertyType.SINGLE_FAMILY,
        lo: User | None = None,
        **overrides: object,
    ) -> Application:
        # `field_values.overridden_by` FKs to `users.id`, and the override
        # routes now stamp it with the real signed-in staff user's id
        # (phase-p2 merge, H3) -- pass `lo=` (e.g. a `make_staff_session`
        # result's `.user`) to own the application as a specific staff user
        # for auth/scoping tests; a fresh throwaway LO is created otherwise.
        if lo is None:
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
            strategy=strategy,
            requested_price=requested_price,
            **overrides,
        )
        db_session.add(application)
        await db_session.flush()

        if with_property:
            property_ = Property(
                application_id=application.id,
                address_status=PropertyAddressStatus.SPECIFIC_ADDRESS,
                state=state,
                county=county,
                zip=zip_code,
                property_type=property_type,
                number_of_units=1,
            )
            db_session.add(property_)
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
