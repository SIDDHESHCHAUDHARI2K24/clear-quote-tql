"""P3/P4 foundation: `quotes.stale` (migration `bbd0e3150264`)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote


async def _make_scenario(db_session: AsyncSession) -> Scenario:
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
    return scenario


async def test_stale_defaults_to_false(db_session: AsyncSession) -> None:
    scenario = await _make_scenario(db_session)
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
    await db_session.refresh(quote)

    assert quote.stale is False


async def test_stale_is_settable(db_session: AsyncSession) -> None:
    scenario = await _make_scenario(db_session)
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
        stale=True,
    )
    db_session.add(quote)
    await db_session.flush()
    await db_session.refresh(quote)

    assert quote.stale is True
