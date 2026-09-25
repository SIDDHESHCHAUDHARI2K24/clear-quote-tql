"""P3/P4 foundation: `quote_package_versions` (migration `bbd0e3150264`).

Builds its own minimal `users -> clients -> applications -> scenarios ->
quotes -> quote_packages` chain -- CQ-020 (which actually sends packages)
hasn't landed yet, so there is no service-level factory to reuse."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion


async def _make_package(db_session: AsyncSession) -> QuotePackage:
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

    application = Application(client_id=client.id, lo_id=lo.id, occupancy=Occupancy.PRIMARY)
    db_session.add(application)
    await db_session.flush()

    scenario = Scenario(application_id=application.id, inputs={}, config_snapshot={})
    db_session.add(scenario)
    await db_session.flush()

    quote = Quote(
        scenario_id=scenario.id,
        investor="Optimal Blue",
        product="30yr Fixed",
        rate=Decimal("6.500"),
        points=Decimal("0.000"),
        lock_days=30,
        computed={},
        label="Par",
        priced_at=datetime.now(UTC),
    )
    db_session.add(quote)
    await db_session.flush()

    package = QuotePackage(
        application_id=application.id,
        quote_ids=[quote.id],
        report_token=f"draft-{uuid.uuid4()}",
    )
    db_session.add(package)
    await db_session.flush()
    return package


def _version(package: QuotePackage, *, version: int, token: str) -> QuotePackageVersion:
    now = datetime.now(UTC)
    return QuotePackageVersion(
        package_id=package.id,
        version=version,
        snapshot={"hero": {"rate": "6.5"}},
        report_token=token,
        sent_at=now,
        expires_at=now + timedelta(days=21),
    )


async def test_create_version(db_session: AsyncSession) -> None:
    package = await _make_package(db_session)
    version = _version(package, version=1, token=f"tok-{uuid.uuid4()}")
    db_session.add(version)
    await db_session.flush()
    await db_session.refresh(version)

    assert version.superseded is False
    assert version.viewed_at is None
    assert version.borrower_action is None
    assert version.snapshot == {"hero": {"rate": "6.5"}}


async def test_version_number_unique_per_package(db_session: AsyncSession) -> None:
    package = await _make_package(db_session)
    db_session.add(_version(package, version=1, token=f"tok-{uuid.uuid4()}"))
    await db_session.flush()

    db_session.add(_version(package, version=1, token=f"tok-{uuid.uuid4()}"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_version_number_reusable_across_packages(db_session: AsyncSession) -> None:
    """The `(package_id, version)` uniqueness is per package, not global --
    two different packages can each have their own version 1."""
    package_a = await _make_package(db_session)
    package_b = await _make_package(db_session)

    db_session.add(_version(package_a, version=1, token=f"tok-{uuid.uuid4()}"))
    db_session.add(_version(package_b, version=1, token=f"tok-{uuid.uuid4()}"))
    await db_session.flush()  # no IntegrityError


async def test_report_token_globally_unique(db_session: AsyncSession) -> None:
    package = await _make_package(db_session)
    token = f"tok-{uuid.uuid4()}"
    db_session.add(_version(package, version=1, token=token))
    await db_session.flush()

    other_package = await _make_package(db_session)
    db_session.add(_version(other_package, version=1, token=token))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_cascade_delete_on_package(db_session: AsyncSession) -> None:
    package = await _make_package(db_session)
    version = _version(package, version=1, token=f"tok-{uuid.uuid4()}")
    db_session.add(version)
    await db_session.flush()

    await db_session.delete(package)
    await db_session.flush()

    remaining = (
        await db_session.execute(
            select(QuotePackageVersion).where(QuotePackageVersion.id == version.id)
        )
    ).scalar_one_or_none()
    assert remaining is None
