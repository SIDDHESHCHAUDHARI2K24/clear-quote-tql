"""AC7: per-test transaction rollback means no test's writes leak into the next.

CQ-004 has no real domain tables yet (CQ-007 scope), so this declares a
throwaway `Base`-registered table at import time. Because pytest imports
every test module during collection, before any session-scoped fixture
runs, `Base.metadata.create_all` (in `conftest.py`'s `test_engine` fixture)
picks it up like any other model.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class _IsolationProbe(Base):
    __tablename__ = "_isolation_probe_cq004"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str]


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


async def test_rows_do_not_leak_across_tests(test_engine: AsyncEngine) -> None:
    async with _isolated_session(test_engine) as first_session:
        first_session.add(_IsolationProbe(value="from-first"))
        await first_session.commit()

        rows = (await first_session.execute(select(_IsolationProbe))).scalars().all()
        assert [row.value for row in rows] == ["from-first"]

    async with _isolated_session(test_engine) as second_session:
        rows = (await second_session.execute(select(_IsolationProbe))).scalars().all()
        assert rows == []

        second_session.add(_IsolationProbe(value="from-second"))
        await second_session.commit()

        rows = (await second_session.execute(select(_IsolationProbe))).scalars().all()
        assert [row.value for row in rows] == ["from-second"]

    async with _isolated_session(test_engine) as third_session:
        rows = (await third_session.execute(select(_IsolationProbe))).scalars().all()
        assert rows == []


async def test_db_session_fixture_itself_rolls_back(db_session: AsyncSession) -> None:
    db_session.add(_IsolationProbe(value="via-fixture"))
    await db_session.commit()

    rows = (await db_session.execute(select(_IsolationProbe))).scalars().all()
    assert [row.value for row in rows] == ["via-fixture"]


async def test_previous_fixture_test_left_no_trace(db_session: AsyncSession) -> None:
    rows = (await db_session.execute(select(_IsolationProbe))).scalars().all()
    assert rows == []
