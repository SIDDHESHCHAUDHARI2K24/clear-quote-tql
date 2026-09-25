"""Shared Valkey (Redis-protocol) client, lazily created from
`Settings.valkey_url`.

CQ-014's OTP challenges, login rate limits and staff sessions (and CQ-015's
borrower equivalents) all live in Valkey, not Postgres — `get_valkey` is the
FastAPI dependency every one of those services takes instead of importing
this module's client directly, so `backend/conftest.py` can override it
with a test-scoped client (see its `valkey` fixture).
"""

from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.core.config import get_settings

_client: Redis | None = None


def _get_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().valkey_url, decode_responses=True)
    return _client


async def get_valkey() -> AsyncIterator[Redis]:
    yield _get_client()


async def close_valkey() -> None:
    """Closes the shared client; called from the app's shutdown handler."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
