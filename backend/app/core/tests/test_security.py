"""CQ-014 T2: password hashing, OTP generation and token primitives."""

import re

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    constant_time_equals,
    generate_otp_code,
    generate_token,
    hash_password,
    hash_password_async,
    hash_token,
    keyed_hash,
    verify_password,
    verify_password_async,
)


def test_hash_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password(hashed, "correct horse battery staple") is True


def test_verify_wrong_password_returns_false() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password(hashed, "wrong password") is False


def test_verify_garbage_hash_returns_false() -> None:
    assert verify_password("not-a-real-argon2-hash", "anything") is False


def test_verify_corrupted_argon2_shaped_hash_returns_false() -> None:
    # Starts with a valid argon2id prefix but the payload fails to decode
    # (truncated/corrupted) — a different failure path than a wholly
    # foreign string (InvalidHashError vs VerificationError).
    assert verify_password("$argon2id$v=19$m=65536,t=3,p=4$garbage", "anything") is False


def test_dummy_password_hash_never_verifies() -> None:
    assert verify_password(DUMMY_PASSWORD_HASH, "anything") is False


def test_otp_code_is_six_digits() -> None:
    code = generate_otp_code()
    assert re.fullmatch(r"\d{6}", code)


def test_otp_code_varies() -> None:
    codes = {generate_otp_code() for _ in range(20)}
    assert len(codes) > 1


def test_hash_token_deterministic() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")


def test_generate_token_urlsafe_and_random() -> None:
    a = generate_token()
    b = generate_token()
    assert a != b
    assert re.fullmatch(r"[A-Za-z0-9_-]+", a)


def test_constant_time_equals() -> None:
    assert constant_time_equals("abc", "abc") is True
    assert constant_time_equals("abc", "abd") is False


async def test_hash_password_async_roundtrips_with_verify_password_async() -> None:
    hashed = await hash_password_async("correct horse battery staple")
    assert await verify_password_async(hashed, "correct horse battery staple") is True


async def test_verify_password_async_wrong_password_returns_false() -> None:
    hashed = await hash_password_async("correct horse battery staple")
    assert await verify_password_async(hashed, "wrong password") is False


async def test_hash_password_async_produces_a_hash_verify_password_accepts() -> None:
    # The async and sync helpers hash/verify the same way underneath —
    # only the thread offload differs.
    hashed = await hash_password_async("correct horse battery staple")
    assert verify_password(hashed, "correct horse battery staple") is True


async def test_verify_password_async_accepts_a_sync_hash_password_hash() -> None:
    hashed = hash_password("correct horse battery staple")
    assert await verify_password_async(hashed, "correct horse battery staple") is True


async def test_verify_password_async_garbage_hash_returns_false() -> None:
    assert await verify_password_async("not-a-real-argon2-hash", "anything") is False


async def test_valkey_fixture_set_get(valkey: Redis) -> None:
    await valkey.set("cq:test:key", "value")
    assert await valkey.get("cq:test:key") == "value"


def test_cookie_secure_false_under_test_env() -> None:
    assert get_settings().app_env == "test"
    assert get_settings().cookie_secure is False


def test_keyed_hash_is_deterministic_and_not_plain_sha256() -> None:
    assert keyed_hash("123456") == keyed_hash("123456")
    assert keyed_hash("123456") != hash_token("123456")
