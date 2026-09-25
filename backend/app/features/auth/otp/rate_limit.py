"""Fixed-window rate limiting on top of Valkey: `INCR` + self-healing `EXPIRE NX`.

`hit` is the general primitive (plan.md Decision #6); `check_login` and
`check_signup` apply it to the per-email/per-IP windows for their action
(CQ-015 plan.md Decision #8, revised). Both share `_check_action`'s key
shape (`rl:{principal}:{action}:...`) but never share a counter with each
other, so a flood against one action can't lock the other out — a sign-up
flood for someone's email can't lock them out of login (and vice versa).
"""

from typing import Literal

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.errors import RateLimitedError

_RATE_LIMITED_MESSAGE = "Too many attempts. Try again later."

_Action = Literal["login", "signup"]


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


async def _check_action(
    valkey: Redis, *, principal: str, action: _Action, email: str, ip: str
) -> None:
    """Applies both the per-email and per-IP rate limits for `action`:
    `rl:{principal}:{action}:email:{email}` and
    `rl:{principal}:{action}:ip:{ip}`. Either one tripping raises. Both
    actions use the same limits (CQ-015 plan.md Decision #8, revised); only
    the key — and therefore the counter — differs.
    """
    settings = get_settings()
    await hit(
        valkey,
        f"rl:{principal}:{action}:email:{email}",
        limit=settings.login_rate_limit_per_email,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    await hit(
        valkey,
        f"rl:{principal}:{action}:ip:{ip}",
        limit=settings.login_rate_limit_per_ip,
        window_seconds=settings.login_rate_limit_window_seconds,
    )


async def check_login(valkey: Redis, *, principal: str, email: str, ip: str) -> None:
    """Applies both the per-email and per-IP login rate limits (Decision
    #6): `rl:{principal}:login:email:{email}` and
    `rl:{principal}:login:ip:{ip}`. Either one tripping raises.
    """
    await _check_action(valkey, principal=principal, action="login", email=email, ip=ip)


async def check_signup(valkey: Redis, *, principal: str, email: str, ip: str) -> None:
    """Applies both the per-email and per-IP sign-up rate limits (CQ-015
    plan.md Decision #8, revised): `rl:{principal}:signup:email:{email}`
    and `rl:{principal}:signup:ip:{ip}` — separate counters from
    `check_login`'s, using the same limits, so a flood of sign-ups for
    someone's email can't lock them out of logging in.
    """
    await _check_action(valkey, principal=principal, action="signup", email=email, ip=ip)
