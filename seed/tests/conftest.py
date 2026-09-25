"""Fixtures for `seed/tests/*` -- mirrors `backend/conftest.py`'s
`test_engine`/`db_session` pattern exactly (own copy, not an import: `seed/`
is a sibling of `backend/`, not nested under it, so pytest's automatic
conftest discovery for `backend/conftest.py` doesn't reach here).
"""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("INTEGRATION_LATENCY_ENABLED", "false")

import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from seed.loader import (  # noqa: E402
    PersonaSeedResult,
    UserSeedResult,
    load_persona_fixtures,
    seed_persona,
    seed_providers,
    seed_users,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _upgrade_to_head(database_url: str) -> None:
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


@dataclass
class SeededBase:
    db: AsyncSession
    users: UserSeedResult
    personas: list[dict[str, Any]]
    persona_results: list[PersonaSeedResult]


@pytest_asyncio.fixture
async def seeded_base(db_session: AsyncSession) -> SeededBase:
    """Seeds users + all `provider_*` fixture rows + all 10 personas (import
    -> verify only -- no documents/background apps, which have their own
    lighter-weight fixtures) against `db_session`'s savepoint-wrapped
    transaction, so every test using this fixture starts from the same
    state and nothing survives past the test."""
    user_result = await seed_users(db_session)
    await seed_providers(db_session)

    personas = load_persona_fixtures()
    persona_results: list[PersonaSeedResult] = []
    for i, persona in enumerate(personas):
        lo_id = user_result.lo_ids[i % len(user_result.lo_ids)]
        result = await seed_persona(db_session, persona, lo_id=lo_id, s3_client=None)
        persona_results.append(result)

    return SeededBase(
        db=db_session, users=user_result, personas=personas, persona_results=persona_results
    )
