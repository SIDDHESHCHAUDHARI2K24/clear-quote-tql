"""Email OTP challenges: issue, verify, single-use, attempt-limited.

Principal-agnostic (plan.md Decision #8) so CQ-015's borrower flow reuses
this module instead of copying it: `principal` is stored on the Valkey hash
and checked on verify, so a challenge issued for one principal can never be
verified against the other. `extra` lets a caller (e.g. CQ-015's signup)
carry a few extra string fields through the challenge alongside `subject_id`.
"""

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.core.security import constant_time_equals, generate_otp_code, generate_token, keyed_hash
from app.features.auth.principal import Principal
from app.features.auth.valkey_decode import decode_value

_INVALID_OR_EXPIRED = "Invalid or expired code"
# Internal bookkeeping fields stored on the Valkey hash that `verify_challenge`
# never returns to its caller — only `subject_id` and any `extra` fields
# passed to `issue_challenge` come back, per its docstring.
_RESERVED_FIELDS = {"principal", "code_hash", "attempts"}

# Runs the wrong-code bump atomically so a key that's gone by the time this
# executes (deleted by a concurrent successful verify, or expired between
# this call's own `HGETALL` and here) is never recreated: without this, a
# bare `HINCRBY` on a missing key would silently create a new hash with
# just `attempts` set and no TTL, which then never expires. `EXISTS` +
# `HINCRBY` + a conditional `DEL` all run as one Valkey operation, so no
# other command can interleave between the existence check and the bump.
_BUMP_ATTEMPTS_IF_PRESENT_SCRIPT = """
if redis.call("EXISTS", KEYS[1]) == 0 then
    return -1
end
local attempts = redis.call("HINCRBY", KEYS[1], "attempts", 1)
if attempts >= tonumber(ARGV[1]) then
    redis.call("DEL", KEYS[1])
end
return attempts
"""


def _key(challenge_id: str) -> str:
    return f"otp:{challenge_id}"


async def issue_challenge(
    valkey: Redis,
    *,
    principal: Principal,
    subject_id: str,
    extra: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Creates a new OTP challenge; returns `(challenge_id, code)`.

    `code` is the plaintext 6-digit code for the caller to email out — only
    its keyed hash is stored in Valkey.
    """
    settings = get_settings()
    challenge_id = generate_token(24)
    code = generate_otp_code()

    # `extra` is applied first so it can never clobber the reserved
    # bookkeeping fields below (e.g. a caller passing `extra={"principal":
    # "staff"}` must not be able to forge the stored principal).
    fields: dict[str, str] = dict(extra) if extra else {}
    fields.update(
        {
            "principal": principal,
            "subject_id": subject_id,
            "code_hash": keyed_hash(code),
            "attempts": "0",
        }
    )

    key = _key(challenge_id)
    # HSET then EXPIRE inside one transactional pipeline so the two writes
    # land atomically — otherwise a crash/timing gap between them could
    # leave the hash with no TTL (never expires) or none at all (never
    # readable).
    async with valkey.pipeline(transaction=True) as pipe:
        # redis-py's `mapping` param type is invariant in its Union value
        # type, so a concrete `dict[str, str]` (matching
        # `decode_responses=True`) never structurally matches it — see
        # `_decode`'s docstring for the same decode_responses-vs-typing
        # mismatch.
        pipe.hset(key, mapping=fields)  # type: ignore[arg-type]
        pipe.expire(key, settings.otp_ttl_seconds)
        await pipe.execute()
    return challenge_id, code


async def verify_challenge(
    valkey: Redis,
    *,
    principal: Principal,
    challenge_id: str,
    code: str,
) -> dict[str, str]:
    """Verifies `code` against the stored challenge; returns the stored
    fields (`subject_id` and any `extra` passed to `issue_challenge`, minus
    the internal `code_hash`/`attempts` bookkeeping) on success.

    Single use: the key is deleted as soon as the right code is presented,
    and that delete is what decides success — if it finds the key already
    gone (a concurrent verify's delete won the race), this call loses and
    raises too, so two concurrent correct verifies can never both succeed.
    A wrong code bumps `attempts` and deletes the key once
    `otp_max_attempts` is reached, so a later correct code can't revive a
    spent challenge; that bump runs in a single atomic Valkey script (see
    `_BUMP_ATTEMPTS_IF_PRESENT_SCRIPT`) so a key that's disappeared between
    this call's `HGETALL` above and the bump (deleted by a concurrent
    verify, or expired) is never recreated. A missing key, a principal
    mismatch, or a wrong code all raise the identical `AuthenticationError`
    so a caller can't use the response to distinguish "expired" from
    "wrong code" from "wrong principal".
    """
    settings = get_settings()
    key = _key(challenge_id)
    raw_stored = await valkey.hgetall(key)
    stored = {decode_value(field): decode_value(value) for field, value in raw_stored.items()}
    if not stored or stored.get("principal") != principal:
        raise AuthenticationError(_INVALID_OR_EXPIRED)

    if not constant_time_equals(stored["code_hash"], keyed_hash(code)):
        await valkey.eval(_BUMP_ATTEMPTS_IF_PRESENT_SCRIPT, 1, key, str(settings.otp_max_attempts))
        raise AuthenticationError(_INVALID_OR_EXPIRED)

    deleted = await valkey.delete(key)
    if deleted != 1:
        raise AuthenticationError(_INVALID_OR_EXPIRED)
    return {field: value for field, value in stored.items() if field not in _RESERVED_FIELDS}
