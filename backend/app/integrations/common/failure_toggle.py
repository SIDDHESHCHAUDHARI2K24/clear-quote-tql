"""Per-adapter forced-failure toggle, stored in Valkey.

**Decision** (spec.md): lives in Valkey, not the `settings` table, so
CQ-029's Integration panel can flip it instantly without touching Postgres,
and it resets on `make demo-reset` without a migration. Key shape:
`integration:fail:{adapter}` (string `"1"`/`"0"`, no TTL).

The module-level `_client` is a lazily-created `redis.asyncio.Redis` bound
to `Settings.valkey_url`. `backend/app/integrations/conftest.py` replaces it
with an in-process `fakeredis` client for the whole test session (see its
docstring for why), so production code here never has to know or care
which one it's talking to.
"""

import redis.asyncio as redis

from app.core.config import get_settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().valkey_url, decode_responses=True)
    return _client


def _key(adapter: str) -> str:
    return f"integration:fail:{adapter}"


async def is_forced_to_fail(adapter: str) -> bool:
    value = await _get_client().get(_key(adapter))
    return value == "1"


async def set_forced_failure(adapter: str, enabled: bool) -> None:
    await _get_client().set(_key(adapter), "1" if enabled else "0")
