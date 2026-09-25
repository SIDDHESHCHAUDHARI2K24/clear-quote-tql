"""Shared pytest fixtures for every feature's `tests/` package.

- `db_session`: opens a connection against `TEST_DATABASE_URL`, begins an
  outer transaction, binds an `AsyncSession` to that connection (using
  `join_transaction_mode="create_savepoint"` so an inner `session.commit()`
  releases a savepoint instead of ending the outer transaction), yields the
  session, then rolls back and closes — so no test's writes survive into
  the next test.
- `app`: the FastAPI app instance.
- `client`: an `httpx.AsyncClient` wired to that app with `get_db`
  overridden to hand out the per-test `db_session`.

CQ-004 has no real tables yet, so `Base.metadata.create_all` (run once per
session) is the table setup. CQ-007 replaces this with
`alembic upgrade head` against the test DB once real models exist.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.db import Base, get_db
from app.main import app as fastapi_app


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().test_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as conn:
        outer_transaction = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()


@pytest_asyncio.fixture
async def app() -> AsyncIterator[FastAPI]:
    yield fastapi_app


@pytest_asyncio.fixture
async def client(app: FastAPI, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.pop(get_db, None)
