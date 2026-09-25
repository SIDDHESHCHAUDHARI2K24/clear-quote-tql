"""Shared pytest fixtures for every feature's `tests/` package.

- `db_session`: opens a connection against `TEST_DATABASE_URL`, begins an
  outer transaction, binds an `AsyncSession` to that connection (using
  `join_transaction_mode="create_savepoint"` so an inner `session.commit()`
  releases a savepoint instead of ending the outer transaction), yields the
  session, then rolls back and closes — so no test's writes survive into
  the next test.
- `app`: the FastAPI app instance.
- `valkey`: a function-scoped `redis.asyncio.Redis` against `VALKEY_URL`,
  `FLUSHDB`d before and after each test.
- `client`: an `httpx.AsyncClient` wired to that app with `get_db` and
  `get_valkey` overridden to hand out the per-test `db_session`/`valkey`.

CQ-007: `test_engine` now runs `alembic upgrade head` against
`TEST_DATABASE_URL` (once per session) instead of CQ-004's
`Base.metadata.create_all`, so tests exercise the real migration path
(AC1/AC5/AC6 all depend on this).

CQ-014: the `valkey` fixture `FLUSHDB`s its db before and after every test,
so it never uses `VALKEY_URL`'s db directly: it uses `TEST_VALKEY_URL` when
set, otherwise `VALKEY_URL` with the db index swapped to 15. That keeps a
`make test` run from wiping the dev server's sessions/OTPs in db 0.

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

`make_staff_session` (phase-p2 merge, H3): a factory fixture that creates a
real staff `User` row plus a real Valkey session for it (via
`app.features.auth.sessions.service.create_session` — the same helper the
staff login flow uses, not a duplicate), and sets the resulting token as the
`client` fixture's `cq_staff_session` cookie. Every pricing/pipeline route
test that used to rely on CQ-013's `DEV_LO_ID` stub now authenticates
through this instead. Calling it again on the same test overwrites the
cookie (i.e. "log out, log in as someone else"), which is exactly what the
LO/Manager scoping tests need.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
# CQ-009: keep the full suite fast; integrations/common/tests/test_latency.py
# monkeypatches this back on for its one enabled-path test.
os.environ.setdefault("INTEGRATION_LATENCY_ENABLED", "false")

import asyncio  # noqa: E402
import uuid  # noqa: E402
from dataclasses import dataclass  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fakeredis import aioredis as fakeredis_aioredis  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.core.valkey import get_valkey  # noqa: E402
from app.features.auth.models import User  # noqa: E402
from app.features.auth.sessions.service import COOKIE_NAMES, create_session  # noqa: E402
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


def _test_valkey_url() -> str:
    settings = get_settings()
    if settings.test_valkey_url:
        return settings.test_valkey_url
    parts = urlsplit(settings.valkey_url)
    return urlunsplit(parts._replace(path="/15"))


@pytest_asyncio.fixture
async def valkey() -> AsyncIterator[Redis]:
    client = Redis.from_url(_test_valkey_url(), decode_responses=True)
    try:
        await client.flushdb()
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def client(
    app: FastAPI, db_session: AsyncSession, valkey: Redis
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_get_valkey() -> AsyncIterator[Redis]:
        yield valkey

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_valkey] = _override_get_valkey
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_valkey, None)


@dataclass(frozen=True)
class StaffSession:
    """`make_staff_session`'s return value: the `User` row it created plus
    the raw session token (rarely needed directly -- it's already set as the
    `client` fixture's cookie)."""

    user: User
    token: str


@pytest_asyncio.fixture
async def make_staff_session(
    db_session: AsyncSession, valkey: Redis, client: AsyncClient
) -> Callable[..., Awaitable[StaffSession]]:
    """Factory fixture (phase-p2 merge, H3): creates a real staff `User` row
    with the given `role` and a real Valkey session for it (via
    `auth.sessions.service.create_session`, the same helper the staff login
    flow uses), and sets the resulting token as the `client` fixture's
    `cq_staff_session` cookie so the next request `client` makes is
    authenticated as that user. Calling it again overwrites the cookie --
    useful for "log in as the owner, then log in as someone else" scoping
    tests.
    """

    async def _make(role: UserRole = UserRole.LO, email: str | None = None) -> StaffSession:
        user = User(
            email=email or f"staff-{uuid.uuid4()}@clearquote-demo.test",
            password_hash="not-a-real-hash",
            role=role,
            full_name="Test Staff",
        )
        db_session.add(user)
        await db_session.flush()

        token = await create_session(valkey, principal="staff", subject_id=str(user.id))
        client.cookies.set(COOKIE_NAMES["staff"], token)
        return StaffSession(user=user, token=token)

    return _make
