"""Factory fixtures for `clients` tests: build the minimum rows the
`clients` queries join against without going through the Temporal pipeline
(mirrors `applications/listing/tests/conftest.py`)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion


@dataclass
class ClientFixture:
    client: Client
    lo: User


MakeLo = Callable[..., Awaitable[User]]
MakeClient = Callable[..., Awaitable[ClientFixture]]
MakeApplicationFor = Callable[..., Awaitable[Application]]


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
async def make_client(db_session: AsyncSession, make_lo: MakeLo) -> MakeClient:
    async def _make(
        *,
        lo: User | None = None,
        full_name: str = "Test Client",
        email: str | None = None,
        phone: str | None = None,
        created_at: datetime | None = None,
    ) -> ClientFixture:
        lo = lo or await make_lo()
        client = Client(
            full_name=full_name,
            email=email or f"{uuid.uuid4()}@example.test",
            phone=phone,
            assigned_lo_id=lo.id,
        )
        db_session.add(client)
        await db_session.flush()
        if created_at is not None:
            client.created_at = created_at
            await db_session.flush()
        return ClientFixture(client=client, lo=lo)

    return _make


@pytest_asyncio.fixture
async def make_application_for(db_session: AsyncSession) -> MakeApplicationFor:
    async def _make(
        client: Client,
        lo: User,
        *,
        status: ApplicationStatus = ApplicationStatus.PRICED,
        strategy: Strategy | None = None,
        requested_price: Decimal | None = Decimal("300000.00"),
        updated_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> Application:
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
        return application

    return _make


async def add_activity_event(
    db: AsyncSession,
    application: Application,
    *,
    type: str = "pipeline.imported",
    actor: str = "system",
    at: datetime | None = None,
    payload: dict | None = None,
) -> ActivityEvent:
    event = ActivityEvent(
        application_id=application.id,
        actor=actor,
        type=type,
        payload=payload,
        at=at or datetime.now(UTC),
    )
    db.add(event)
    await db.flush()
    return event


async def add_sent_version(
    db: AsyncSession,
    application: Application,
    *,
    version: int = 1,
    sent_at: datetime | None = None,
    expires_at: datetime | None = None,
    viewed_at: datetime | None = None,
    superseded: bool = False,
    borrower_action: dict | None = None,
    snapshot: dict | None = None,
) -> QuotePackageVersion:
    sent_at = sent_at or datetime.now(UTC)
    package = QuotePackage(
        application_id=application.id,
        quote_ids=[],
        report_token=str(uuid.uuid4()),
        sent_at=sent_at,
    )
    db.add(package)
    await db.flush()
    row = QuotePackageVersion(
        package_id=package.id,
        version=version,
        snapshot=snapshot or {},
        report_token=str(uuid.uuid4()),
        sent_at=sent_at,
        expires_at=expires_at or sent_at,
        viewed_at=viewed_at,
        superseded=superseded,
        borrower_action=borrower_action,
    )
    db.add(row)
    await db.flush()
    return row
