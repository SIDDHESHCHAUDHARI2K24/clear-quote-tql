"""Local factories for `dashboard/tests/test_dashboard.py`.

`make_application` follows `applications/tests/conftest.py`'s established
pattern (`lo=` lets a test own the application as a specific staff user for
LO/Manager scoping) with an extra `status=` so a test doesn't need a second
round trip to set it.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, ApplicationTab, FlagSeverity, Occupancy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.features.auth.models import User
from app.features.clients.models import Client as ClientModel
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion


@pytest_asyncio.fixture
async def make_application(db_session: AsyncSession) -> Callable[..., Awaitable[Application]]:
    async def _make(
        occupancy: Occupancy = Occupancy.PRIMARY,
        lo: User | None = None,
        status: ApplicationStatus = ApplicationStatus.INTAKE,
        client_name: str = "Test Client",
        updated_at: datetime | None = None,
    ) -> Application:
        if lo is None:
            lo = User(
                email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
                password_hash="not-a-real-hash",
                role=UserRole.LO,
                full_name="Test LO",
            )
            db_session.add(lo)
            await db_session.flush()

        client_row = ClientModel(
            full_name=client_name,
            email=f"client-{uuid.uuid4()}@clearquote-demo.test",
            assigned_lo_id=lo.id,
        )
        db_session.add(client_row)
        await db_session.flush()

        application = Application(
            client_id=client_row.id, lo_id=lo.id, occupancy=occupancy, status=status
        )
        db_session.add(application)
        await db_session.flush()
        if updated_at is not None:
            # Bypass `onupdate=func.now()` -- a raw UPDATE lets a test pin
            # the exact "status changed at" instant the dashboard orders by.
            application.updated_at = updated_at
            await db_session.flush()
        return application

    return _make


@pytest_asyncio.fixture
async def make_flag(db_session: AsyncSession) -> Callable[..., Awaitable[Flag]]:
    async def _make(
        application_id: uuid.UUID,
        *,
        message: str | None,
        resolved: bool = False,
        created_at: datetime | None = None,
        tab: ApplicationTab = ApplicationTab.HOUSING,
        rule: str = "test_rule",
    ) -> Flag:
        flag = Flag(
            application_id=application_id,
            tab=tab,
            field_key="test_field",
            rule=rule,
            severity=FlagSeverity.BLOCKING,
            message=message,
            resolved_at=datetime.now(UTC) if resolved else None,
        )
        db_session.add(flag)
        await db_session.flush()
        if created_at is not None:
            flag.created_at = created_at
            await db_session.flush()
        return flag

    return _make


@pytest_asyncio.fixture
async def make_property(db_session: AsyncSession) -> Callable[..., Awaitable[Property]]:
    async def _make(
        application_id: uuid.UUID,
        address_status: PropertyAddressStatus = PropertyAddressStatus.SPECIFIC_ADDRESS,
    ) -> Property:
        prop = Property(
            application_id=application_id,
            address_status=address_status,
            street_address=(
                "1 Main St" if address_status == PropertyAddressStatus.SPECIFIC_ADDRESS else None
            ),
            property_type=PropertyType.SINGLE_FAMILY,
        )
        db_session.add(prop)
        await db_session.flush()
        return prop

    return _make


@pytest_asyncio.fixture
async def make_recommended_quote(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Quote]]:
    async def _make(application: Application, priced_at: datetime) -> Quote:
        scenario = Scenario(application_id=application.id, inputs={}, config_snapshot={})
        db_session.add(scenario)
        await db_session.flush()

        quote = Quote(
            scenario_id=scenario.id,
            investor="TestInvestor",
            product="30yr Fixed",
            rate=Decimal("7.000"),
            points=Decimal("0"),
            lock_days=30,
            computed={},
            label="Par",
            priced_at=priced_at,
        )
        db_session.add(quote)
        await db_session.flush()

        application.recommended_quote_id = quote.id
        await db_session.flush()
        return quote

    return _make


@pytest_asyncio.fixture
async def make_sent_version(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[QuotePackageVersion]]:
    async def _make(
        application_id: uuid.UUID,
        *,
        sent_at: datetime,
        version: int = 1,
        borrower_action: dict | None = None,
        options: list[dict] | None = None,
    ) -> QuotePackageVersion:
        package = QuotePackage(
            application_id=application_id,
            quote_ids=[],
            report_token=secrets.token_urlsafe(16),
            sent_at=sent_at,
        )
        db_session.add(package)
        await db_session.flush()

        pkg_version = QuotePackageVersion(
            package_id=package.id,
            version=version,
            snapshot={"options": options or []},
            report_token=secrets.token_urlsafe(16),
            sent_at=sent_at,
            expires_at=sent_at,
            borrower_action=borrower_action,
        )
        db_session.add(pkg_version)
        await db_session.flush()
        return pkg_version

    return _make


@pytest_asyncio.fixture
async def make_activity_event(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[ActivityEvent]]:
    async def _make(
        application_id: uuid.UUID, *, actor: str, type_: str, at: datetime
    ) -> ActivityEvent:
        event = ActivityEvent(
            application_id=application_id, actor=actor, type=type_, payload={}, at=at
        )
        db_session.add(event)
        await db_session.flush()
        return event

    return _make
