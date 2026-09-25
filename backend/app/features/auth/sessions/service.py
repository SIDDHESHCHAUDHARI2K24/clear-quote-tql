"""Server-side sessions in Valkey: opaque tokens, sliding TTL, cookie helpers.

Principal-agnostic (plan.md Decision #8): `principal` picks the TTL and the
cookie name, so CQ-015's borrower sessions reuse this module rather than
duplicating it. Only the token's hash is ever stored in Valkey — the raw
token exists only in the cookie and in the return value of
`create_session`.
"""

from fastapi import Response
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.security import generate_token, hash_token
from app.features.auth.principal import Principal
from app.features.auth.valkey_decode import decode_value

COOKIE_NAMES: dict[Principal, str] = {
    "staff": "cq_staff_session",
    "borrower": "cq_borrower_session",
}


def _ttl_seconds(principal: Principal) -> int:
    settings = get_settings()
    if principal == "staff":
        return settings.staff_session_ttl_seconds
    return settings.borrower_session_ttl_seconds


def _key(principal: Principal, token: str) -> str:
    return f"sess:{principal}:{hash_token(token)}"


async def create_session(valkey: Redis, *, principal: Principal, subject_id: str) -> str:
    """Creates a new session for `subject_id`; returns the raw token to set
    in the cookie."""
    token = generate_token()
    await valkey.set(_key(principal, token), subject_id, ex=_ttl_seconds(principal))
    return token


async def get_session_subject(valkey: Redis, *, principal: Principal, token: str) -> str | None:
    """The session's subject id, or `None` if it doesn't exist / has
    expired. A hit refreshes the TTL (sliding session)."""
    key = _key(principal, token)
    raw_subject_id = await valkey.get(key)
    if raw_subject_id is None:
        return None
    await valkey.expire(key, _ttl_seconds(principal))
    return decode_value(raw_subject_id)


async def delete_session(valkey: Redis, *, principal: Principal, token: str) -> None:
    await valkey.delete(_key(principal, token))


def set_session_cookie(response: Response, principal: Principal, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAMES[principal],
        token,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.cookie_secure,
        max_age=_ttl_seconds(principal),
    )


def clear_session_cookie(response: Response, principal: Principal) -> None:
    response.delete_cookie(
        COOKIE_NAMES[principal],
        path="/",
        samesite="lax",
        secure=get_settings().cookie_secure,
    )
