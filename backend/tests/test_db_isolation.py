"""AC7: per-test transaction rollback means no test's writes leak into the next.

Exercises isolation against `settings` — a real table `initial_schema`
creates — instead of an ad-hoc `Base`-registered table.

Review finding #1 (docs/backlog/CQ-007-data-model/post-dev.md): the
previous version of this file declared its own `Base`-registered
`_isolation_probe_cq004` table that no migration created. That worked only
because `test_engine` used to run `Base.metadata.create_all()` (CQ-004).
Once this branch switched `test_engine` to `alembic upgrade head` (so tests
exercise the real migration path, per this item's spec), that table was
never created on a genuinely fresh `cq_test`, and all three tests below
failed with `relation "_isolation_probe_cq004" does not exist` — masked
locally only because a stale copy of the table happened to already exist
from before the switch. Using `settings` means this test needs no
throwaway model on the shared `Base.metadata` at all (keeping
`alembic check` clean), and passes on a truly fresh, freshly-migrated DB.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.features.settings.models import Setting

_PROBE_KEY = "_isolation_probe_test"
"""Distinct from every real default key `seed_settings_defaults` inserts."""


@asynccontextmanager
async def _isolated_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Reproduces `conftest.py`'s `db_session` fixture logic standalone.

    Used twice within a single test to stand in for "two different tests"
    each getting their own connection + outer transaction + rollback, since
    a function-scoped fixture can only be requested once per test.
    """
    async with engine.connect() as conn:
        outer_transaction = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()


async def _probe_values(session: AsyncSession) -> list[object]:
    rows = (await session.execute(select(Setting).where(Setting.key == _PROBE_KEY))).scalars().all()
    return [row.value for row in rows]


async def test_rows_do_not_leak_across_tests(test_engine: AsyncEngine) -> None:
    async with _isolated_session(test_engine) as first_session:
        first_session.add(Setting(key=_PROBE_KEY, value="from-first"))
        await first_session.commit()

        assert await _probe_values(first_session) == ["from-first"]

    async with _isolated_session(test_engine) as second_session:
        assert await _probe_values(second_session) == []

        second_session.add(Setting(key=_PROBE_KEY, value="from-second"))
        await second_session.commit()

        assert await _probe_values(second_session) == ["from-second"]

    async with _isolated_session(test_engine) as third_session:
        assert await _probe_values(third_session) == []


async def test_db_session_fixture_itself_rolls_back(db_session: AsyncSession) -> None:
    db_session.add(Setting(key=_PROBE_KEY, value="via-fixture"))
    await db_session.commit()

    assert await _probe_values(db_session) == ["via-fixture"]


async def test_previous_fixture_test_left_no_trace(db_session: AsyncSession) -> None:
    assert await _probe_values(db_session) == []
