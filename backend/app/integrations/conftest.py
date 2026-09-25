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
"""

import pytest
from fakeredis import aioredis as fakeredis_aioredis

from app.integrations.common import failure_toggle


@pytest.fixture(autouse=True)
def _fake_valkey(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = fakeredis_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(failure_toggle, "_client", fake_client)
