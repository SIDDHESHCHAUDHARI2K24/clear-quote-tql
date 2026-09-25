"""AC4: fixed-window rate limiting (`hit`, and `check_login`'s per-email +
per-IP windows)."""

import asyncio

import pytest
from redis.asyncio import Redis

from app.core.errors import RateLimitedError
from app.features.auth.otp.rate_limit import check_login, check_signup, hit


async def test_hit_allows_up_to_limit(valkey: Redis) -> None:
    for _ in range(3):
        await hit(valkey, "rl:test:key", limit=3, window_seconds=60)


async def test_hit_raises_once_over_limit(valkey: Redis) -> None:
    for _ in range(3):
        await hit(valkey, "rl:test:key", limit=3, window_seconds=60)

    with pytest.raises(RateLimitedError):
        await hit(valkey, "rl:test:key", limit=3, window_seconds=60)


async def test_hit_resets_after_window_expires(valkey: Redis) -> None:
    await hit(valkey, "rl:test:key", limit=1, window_seconds=60)
    with pytest.raises(RateLimitedError):
        await hit(valkey, "rl:test:key", limit=1, window_seconds=60)

    # Simulate the window rolling over.
    await valkey.pexpire("rl:test:key", 1)
    await asyncio.sleep(0.05)

    await hit(valkey, "rl:test:key", limit=1, window_seconds=60)


async def test_check_login_trips_per_email_limit(valkey: Redis) -> None:
    for _ in range(5):
        await check_login(valkey, principal="staff", email="lo@clearquote.test", ip="1.1.1.1")

    with pytest.raises(RateLimitedError):
        await check_login(valkey, principal="staff", email="lo@clearquote.test", ip="2.2.2.2")


async def test_check_login_per_email_limit_is_independent_per_email(valkey: Redis) -> None:
    for _ in range(5):
        await check_login(valkey, principal="staff", email="a@clearquote.test", ip="9.9.9.9")

    # A different email, same IP, hasn't tripped its own per-email window
    # (though the shared IP window is still under its higher limit).
    await check_login(valkey, principal="staff", email="b@clearquote.test", ip="9.9.9.9")


async def test_check_login_trips_per_ip_limit(valkey: Redis) -> None:
    for i in range(20):
        await check_login(valkey, principal="staff", email=f"user{i}@clearquote.test", ip="3.3.3.3")

    with pytest.raises(RateLimitedError):
        await check_login(valkey, principal="staff", email="user21@clearquote.test", ip="3.3.3.3")


async def test_signup_flood_does_not_lock_out_login(valkey: Redis) -> None:
    """Decision #8 (revised): sign-up and login keep separate rate-limit
    counters, so 5 sign-ups for an email don't trip login's counter for
    that same email."""
    email = "flooded@clearquote.test"

    for _ in range(5):
        await check_signup(valkey, principal="borrower", email=email, ip="4.4.4.4")

    # Login for the same email is untouched by the sign-up flood.
    await check_login(valkey, principal="borrower", email=email, ip="5.5.5.5")

    # But the 6th sign-up trips the sign-up counter.
    with pytest.raises(RateLimitedError):
        await check_signup(valkey, principal="borrower", email=email, ip="4.4.4.4")


async def test_check_signup_uses_distinct_keys_from_check_login(valkey: Redis) -> None:
    email = "distinct-keys@clearquote.test"
    ip = "6.6.6.6"

    await check_signup(valkey, principal="borrower", email=email, ip=ip)

    assert await valkey.exists(f"rl:borrower:signup:email:{email}") == 1
    assert await valkey.exists(f"rl:borrower:signup:ip:{ip}") == 1
    assert await valkey.exists(f"rl:borrower:login:email:{email}") == 0
    assert await valkey.exists(f"rl:borrower:login:ip:{ip}") == 0
