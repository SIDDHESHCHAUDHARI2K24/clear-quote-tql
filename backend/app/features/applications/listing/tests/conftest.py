"""Factory fixtures for `listing` tests: build the minimum rows the
listing query joins against (`Client`, `User`, `Application`, `Property`,
`Flag`, `QuotePackage`/`QuotePackageVersion`) without going through the
Temporal pipeline."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, ApplicationTab, FlagSeverity, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.applications.verification.models import Flag
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion


@dataclass
class ApplicationFixture:
    application: Application
    client: Client
    lo: User


MakeLo = Callable[..., Awaitable[User]]
MakeClient = Callable[..., Awaitable[Client]]
MakeApplication = Callable[..., Awaitable[ApplicationFixture]]


@pytest_asyncio.fixture
async def make_lo(db_session: AsyncSession) -> MakeLo:
    async def _make(full_name: str = "Test LO", role: UserRole = UserRole.LO) -> User:
        user = User(
            email=f"{uuid.uuid4()}@clearquote.test",
            password_hash="x",
            role=role,
            full_name=full_name,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _make


@pytest_asyncio.fixture
async def make_client(db_session: AsyncSession) -> MakeClient:
    async def _make(lo: User, full_name: str = "Test Client", email: str | None = None) -> Client:
        client = Client(
            full_name=full_name,
            email=email or f"{uuid.uuid4()}@example.test",
            assigned_lo_id=lo.id,
        )
        db_session.add(client)
        await db_session.flush()
        return client

    return _make


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession, make_lo: MakeLo, make_client: MakeClient
) -> MakeApplication:
    async def _make(
        *,
        lo: User | None = None,
        client_name: str = "Test Client",
        client_email: str | None = None,
        status: ApplicationStatus = ApplicationStatus.PRICED,
        strategy: Strategy | None = None,
        requested_price: Decimal | None = Decimal("300000.00"),
        updated_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> ApplicationFixture:
        lo = lo or await make_lo()
        client = await make_client(lo, full_name=client_name, email=client_email)
        application = Application(
            client_id=client.id,
            lo_id=lo.id,
            status=status,
            strategy=strategy,
            requested_price=requested_price,
        )
        db_session.add(application)
        await db_session.flush()
        if updated_at is not None:
            application.updated_at = updated_at
        if created_at is not None:
            application.created_at = created_at
        if updated_at is not None or created_at is not None:
            await db_session.flush()
        return ApplicationFixture(application=application, client=client, lo=lo)

    return _make


async def add_specific_property(
    db: AsyncSession,
    application: Application,
    *,
    street_address: str = "1 Main St",
    city: str = "Denver",
    state: str = "CO",
) -> Property:
    prop = Property(
        application_id=application.id,
        address_status=PropertyAddressStatus.SPECIFIC_ADDRESS,
        street_address=street_address,
        city=city,
        state=state,
        zip="80202",
        property_type=PropertyType.SINGLE_FAMILY,
    )
    db.add(prop)
    await db.flush()
    return prop


async def add_tbd_property(
    db: AsyncSession,
    application: Application,
    *,
    buy_box_states: list[str] | None = None,
    buy_box_metros: list[str] | None = None,
) -> Property:
    prop = Property(
        application_id=application.id,
        address_status=PropertyAddressStatus.TBD,
        property_type=PropertyType.SINGLE_FAMILY,
        buy_box_states=buy_box_states or ["FL"],
        buy_box_metros=buy_box_metros or ["Davenport", "Orlando"],
    )
    db.add(prop)
    await db.flush()
    return prop


async def add_flag(
    db: AsyncSession,
    application: Application,
    *,
    rule: str = "ob_required_field",
    field_key: str = "occupancy_type",
    resolved: bool = False,
) -> Flag:
    flag = Flag(
        application_id=application.id,
        tab=ApplicationTab.BORROWERS,
        field_key=field_key,
        rule=rule,
        severity=FlagSeverity.BLOCKING,
        message="Cannot price: missing Occupancy",
        resolved_at=datetime.now(UTC) if resolved else None,
    )
    db.add(flag)
    await db.flush()
    return flag


async def add_sent_quote_package(
    db: AsyncSession,
    application: Application,
    *,
    sent_at: datetime | None = None,
) -> QuotePackage:
    """A frozen send (P3/P4 foundation D2): a `QuotePackage` plus one
    `QuotePackageVersion` -- the "has this application ever been sent?"
    signal `build_sent_or_later_filter` relies on."""
    sent_at = sent_at or datetime.now(UTC)
    package = QuotePackage(
        application_id=application.id,
        quote_ids=[],
        report_token=str(uuid.uuid4()),
        sent_at=sent_at,
    )
    db.add(package)
    await db.flush()
    version = QuotePackageVersion(
        package_id=package.id,
        version=1,
        snapshot={},
        report_token=str(uuid.uuid4()),
        sent_at=sent_at,
        expires_at=sent_at,
    )
    db.add(version)
    await db.flush()
    return package
