"""P3/P4 foundation (docs/backlog/phase-p3-p4-foundation.md, migration
`bbd0e3150264`): `applications.last_pipeline_stage` and
`applications.recommended_quote_id`.

Uses `make_application` from this package's `conftest.py`; builds its own
minimal `scenarios` -> `quotes` chain for the FK/`ON DELETE SET NULL` case.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import Application
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote


async def _make_quote(db_session: AsyncSession, application: Application) -> Quote:
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
    return quote


async def test_last_pipeline_stage_defaults_to_null(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    assert application.last_pipeline_stage is None


async def test_last_pipeline_stage_is_settable(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    application.last_pipeline_stage = "enrich"
    await db_session.flush()
    await db_session.refresh(application)
    assert application.last_pipeline_stage == "enrich"


async def test_recommended_quote_id_defaults_to_null(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    assert application.recommended_quote_id is None


async def test_recommended_quote_id_set_null_on_quote_delete(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    """`ON DELETE SET NULL`: deleting the recommended quote must not delete
    (or block deleting) the application -- it just clears the pointer."""
    application = await make_application()
    quote = await _make_quote(db_session, application)

    application.recommended_quote_id = quote.id
    await db_session.flush()

    await db_session.delete(quote)
    await db_session.flush()

    # `db_session` runs with `expire_on_commit=False`, so `application`'s
    # in-memory `recommended_quote_id` still holds the pre-delete value
    # until something refreshes it -- the DB-side `ON DELETE SET NULL`
    # already happened (checked here), independent of the ORM's identity
    # map. `refresh()` (not `expire()` + a later attribute touch) is the
    # async-safe way to pull it back in this session.
    await db_session.refresh(application)
    assert application.recommended_quote_id is None


async def test_recommended_quote_id_rejects_unknown_quote(
    db_session: AsyncSession, make_application: Callable[..., Awaitable[Application]]
) -> None:
    application = await make_application()
    application.recommended_quote_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
