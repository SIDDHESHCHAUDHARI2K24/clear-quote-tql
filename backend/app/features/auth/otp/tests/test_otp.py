"""AC3: OTP challenges are single-use, expire, and lock out after too many
wrong attempts; a challenge issued for one principal can't verify against
another."""

import asyncio

import pytest
from redis.asyncio import Redis

from app.core.errors import AuthenticationError
from app.features.auth.otp.service import issue_challenge, verify_challenge


async def test_issue_then_verify_returns_stored_fields(valkey: Redis) -> None:
    challenge_id, code = await issue_challenge(
        valkey, principal="staff", subject_id="user-1", extra={"foo": "bar"}
    )

    fields = await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)

    assert fields["subject_id"] == "user-1"
    assert fields["foo"] == "bar"
    assert "code_hash" not in fields
    assert "attempts" not in fields


async def test_verify_is_single_use(valkey: Redis) -> None:
    challenge_id, code = await issue_challenge(valkey, principal="staff", subject_id="user-1")

    await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)

    with pytest.raises(AuthenticationError):
        await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)


async def test_unknown_challenge_id_rejected(valkey: Redis) -> None:
    with pytest.raises(AuthenticationError):
        await verify_challenge(
            valkey, principal="staff", challenge_id="does-not-exist", code="000000"
        )


async def test_wrong_principal_rejected(valkey: Redis) -> None:
    challenge_id, code = await issue_challenge(valkey, principal="staff", subject_id="user-1")

    with pytest.raises(AuthenticationError):
        await verify_challenge(valkey, principal="borrower", challenge_id=challenge_id, code=code)


async def test_expired_challenge_rejected(valkey: Redis) -> None:
    challenge_id, code = await issue_challenge(valkey, principal="staff", subject_id="user-1")

    await valkey.pexpire(f"otp:{challenge_id}", 1)
    await asyncio.sleep(0.05)

    with pytest.raises(AuthenticationError):
        await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)


async def test_attempts_exhausted_locks_out_even_the_right_code(valkey: Redis) -> None:
    challenge_id, code = await issue_challenge(valkey, principal="staff", subject_id="user-1")

    for _ in range(5):
        with pytest.raises(AuthenticationError):
            await verify_challenge(
                valkey, principal="staff", challenge_id=challenge_id, code="000000"
            )

    with pytest.raises(AuthenticationError):
        await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)


async def test_wrong_code_does_not_consume_the_challenge_before_the_limit(valkey: Redis) -> None:
    challenge_id, code = await issue_challenge(valkey, principal="staff", subject_id="user-1")

    with pytest.raises(AuthenticationError):
        await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code="000000")

    fields = await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)
    assert fields["subject_id"] == "user-1"


async def test_extra_cannot_override_reserved_fields(valkey: Redis) -> None:
    """A caller-supplied `extra` must never be able to forge the stored
    `principal` (or clobber `code_hash`/`attempts`) — otherwise a challenge
    issued for one principal could be smuggled through as another."""
    challenge_id, code = await issue_challenge(
        valkey,
        principal="borrower",
        subject_id="user-1",
        extra={"principal": "staff", "code_hash": "forged", "attempts": "99"},
    )

    # The forged "staff" principal in `extra` must not win: verifying as
    # "staff" still fails...
    with pytest.raises(AuthenticationError):
        await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)

    # ...while the real principal ("borrower") with the real code succeeds:
    # `extra`'s forged "principal"/"code_hash"/"attempts" were overwritten
    # by the real bookkeeping values, not merged over them, and none of
    # the reserved fields leak into the returned dict either way.
    fields = await verify_challenge(
        valkey, principal="borrower", challenge_id=challenge_id, code=code
    )
    assert fields == {"subject_id": "user-1"}
