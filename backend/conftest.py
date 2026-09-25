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

CQ-007: `test_engine` now runs `alembic upgrade head` against
`TEST_DATABASE_URL` (once per session) instead of CQ-004's
`Base.metadata.create_all`, so tests exercise the real migration path
(AC1/AC5/AC6 all depend on this).

The two `os.environ.setdefault` calls below must run before anything below
them imports `app.core.db` (which calls `get_settings()` at *module* import
time to build its module-level engine) or `app.main` — `get_settings()` is
`@lru_cache`d, so whatever `Settings` sees on its first construction is
final for the whole test session:

- `APP_ENV=test` lets `core/config.py`'s fail-fast validator (AC4) skip
  requiring `FIELD_ENCRYPTION_KEY` for tests that never touch
  `application_parties.ssn_encrypted`.
- `FIELD_ENCRYPTION_KEY` still gets a real generated value so tests that DO
  exercise encryption (`app/core/tests/test_encryption.py`) work the same
  whether or not a developer's local `.env` happens to define one — CI
  (CQ-006) isn't guaranteed to load `.env` at all.
- `DEV_LO_ID` (CQ-013): same reasoning as `FIELD_ENCRYPTION_KEY` above —
  every pricing route depends on `deps.get_current_lo_stub()`, which 401s
  when this is unset (AC11's own point), so the *rest* of the suite (routes
  that aren't specifically testing the unset-401 case) needs a real default
  regardless of whether `.env`/the CI workflow happen to define one.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

from cryptography.fernet import Fernet

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
# CQ-009: keep the full suite fast; integrations/common/tests/test_latency.py
# monkeypatches this back on for its one enabled-path test.
os.environ.setdefault("INTEGRATION_LATENCY_ENABLED", "false")
# CQ-013: fixed dev LO id `pricing.scenarios.deps.get_current_lo_stub()`
# returns; `test_auth_stub.py`'s unset-DEV_LO_ID tests monkeypatch
# `get_settings` directly rather than unsetting this env var.
os.environ.setdefault("DEV_LO_ID", "00000000-0000-0000-0000-000000000001")

import asyncio  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fakeredis import aioredis as fakeredis_aioredis  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.integrations.common import failure_toggle  # noqa: E402
from app.integrations.common.models import IntegrationCall  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def _upgrade_to_head(database_url: str) -> None:
    """Runs synchronously in a worker thread (see `test_engine` below) so
    `alembic/env.py`'s own `asyncio.run(...)` doesn't collide with the
    already-running pytest-asyncio session event loop.

    `sqlalchemy_url` in `Config.attributes` is alembic's documented escape
    hatch for handing `env.py` a URL programmatically — `env.py` prefers it
    over `get_settings().database_url` when present, which is what lets
    this target `TEST_DATABASE_URL` instead of the dev database.
    """
    alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    alembic_cfg.attributes["sqlalchemy_url"] = database_url
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    test_database_url = get_settings().test_database_url
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _upgrade_to_head, test_database_url)

    engine = create_async_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def _fake_valkey(monkeypatch: pytest.MonkeyPatch) -> None:
    """CQ-009 Decision (moved up from `app/integrations/conftest.py` by
    CQ-013 so `pricing`/`quotes` feature tests -- which also exercise mock
    adapters through `failure_toggle.is_forced_to_fail` -- get an isolated
    in-process fake instead of the real, possibly-shared local Valkey."""
    fake_client = fakeredis_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(failure_toggle, "_client", fake_client)


@pytest_asyncio.fixture(autouse=True)
async def _clean_integration_calls(test_engine: AsyncEngine) -> AsyncIterator[None]:
    """CQ-009 Decision (moved up, see `_fake_valkey`): `common.logging.
    record_call` commits through its own short-lived session, independent of
    `db_session`'s rollback-based isolation, so it leaves a real row behind
    that nothing else cleans up. Truncate after every test instead."""
    yield
    async with test_engine.begin() as conn:
        await conn.execute(delete(IntegrationCall))


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
