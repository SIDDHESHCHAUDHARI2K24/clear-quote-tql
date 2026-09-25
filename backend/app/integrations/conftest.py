"""Test-only override for `common.failure_toggle`'s Valkey client.

**Decision** (plan.md #1): every test under `app/integrations/` gets an
in-process `fakeredis` client instead of the real local Valkey, for two
reasons. First, `.github/workflows/ci.yml`'s backend job starts a Postgres
service but no Redis/Valkey service, so a real `redis.asyncio` connection
would simply fail in CI. Second, the local `clear-quote` Valkey (port 6379)
is a shared stack other parallel agents' sessions may be using at the same
time; a real connection would let one agent's `set_forced_failure` calls
leak into another's test run. `fakeredis` gives every test function its own
isolated instance with no external dependency either way.

Autouse + function-scoped: `monkeypatch` reverts `failure_toggle._client`
after each test, so no state (or fake connection) survives between tests.

Also holds `_clean_integration_calls`: `common.logging.record_call` writes
its audit row through its own short-lived session/connection, independent
of the per-test `db_session` fixture's rollback-based isolation (see
`logging.py`'s docstring for why -- the row must survive a caller rollback,
so it can't live inside the same transaction that gets rolled back). That
means it's a real, committed row that `db_session`'s teardown can't clean
up for us; this fixture truncates `integration_calls` after every test
instead, the same way `db_session`'s rollback keeps everything else
isolated.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeredis_aioredis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from app.integrations.common import failure_toggle
from app.integrations.common.models import IntegrationCall


@pytest.fixture(autouse=True)
def _fake_valkey(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = fakeredis_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(failure_toggle, "_client", fake_client)


@pytest_asyncio.fixture(autouse=True)
async def _clean_integration_calls(test_engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with test_engine.begin() as conn:
        await conn.execute(delete(IntegrationCall))
