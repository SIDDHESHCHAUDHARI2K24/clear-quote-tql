"""Fixed-window rate limiting on top of Valkey: `INCR` + self-healing `EXPIRE NX`.

`hit` is the general primitive (plan.md Decision #6); `check_login` applies
it to the two login-specific windows (per-email, per-IP) every principal's
login endpoint needs.
"""

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.errors import RateLimitedError

_RATE_LIMITED_MESSAGE = "Too many attempts. Try again later."


async def hit(valkey: Redis, key: str, *, limit: int, window_seconds: int) -> None:
    """Increments `key`'s counter, starting its expiry window on the first
    hit. Raises `RateLimitedError` once the count exceeds `limit`; the
    counter (and its TTL) are left as-is either way so repeated hits in the
    same window keep tripping the limit until the window rolls over.

    `INCR` and `EXPIRE` are two separate Valkey calls, so `expire(..., nx=
    True)` — "set the TTL only if this key doesn't have one yet" — runs on
    *every* hit rather than only when `count == 1`: if a previous call's
    `INCR` landed but its `EXPIRE` never did (crash/timeout between the
    two), the key would otherwise keep incrementing forever with no TTL,
    permanently rate-limiting whoever owns it. The extra round trip on
    every hit (rather than only the first) is a cheap no-op once a TTL is
    already set, and buys self-healing instead of a permanently-stuck
    counter.
    """
    count = await valkey.incr(key)
    await valkey.expire(key, window_seconds, nx=True)
    if count > limit:
        raise RateLimitedError(_RATE_LIMITED_MESSAGE)


async def check_login(valkey: Redis, *, principal: str, email: str, ip: str) -> None:
    """Applies both the per-email and per-IP login rate limits (Decision
    #6): `rl:{principal}:login:email:{email}` and
    `rl:{principal}:login:ip:{ip}`. Either one tripping raises.
    """
    settings = get_settings()
    await hit(
        valkey,
        f"rl:{principal}:login:email:{email}",
        limit=settings.login_rate_limit_per_email,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    await hit(
        valkey,
        f"rl:{principal}:login:ip:{ip}",
        limit=settings.login_rate_limit_per_ip,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
