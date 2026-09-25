"""Staff login: rate limit -> password check -> OTP issue + email; OTP
verify -> signed-in `User`.

Timing/enumeration (plan.md Decision #4): an unknown email still runs a
dummy argon2 verify so an unknown-email response takes the same time, and
returns the identical `AuthenticationError`, as a known-email/wrong-password
response (AC2) — the OTP step is never reached for either.
"""

import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError
from app.core.security import DUMMY_PASSWORD_HASH, verify_password
from app.features.auth.models import User
from app.features.auth.otp.rate_limit import check_login
from app.features.auth.otp.service import issue_challenge, verify_challenge
from app.features.auth.users.service import normalize_email
from app.features.notifications.email.service import send_email

_BAD_CREDENTIALS = "Invalid email or password"

_OTP_EMAIL_HTML = (
    "<p>Your Clear Quote sign-in code is <strong>{code}</strong>.</p>"
    "<p>This code expires in 5 minutes.</p>"
)


async def login(
    db: AsyncSession,
    valkey: Redis,
    *,
    email: str,
    password: str,
    ip: str,
) -> str:
    """Verifies credentials and, on success, issues an OTP challenge and
    emails the code. Returns the `challenge_id`.

    Raises `RateLimitedError` (before touching the DB) if the email or IP
    is over the login rate limit, and `AuthenticationError` with the same
    message for an unknown email or a wrong password.

    `email` is normalized once, up front, so the rate limit and the user
    lookup key off the same value — otherwise case/whitespace variants of
    the same address (`"LO@x"` vs `"lo@x"`) would each get their own
    rate-limit counter instead of sharing one.
    """
    normalized_email = normalize_email(email)
    await check_login(valkey, principal="staff", email=normalized_email, ip=ip)

    user = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()

    if user is None:
        # Dummy verify so timing doesn't reveal whether the email exists.
        verify_password(DUMMY_PASSWORD_HASH, password)
        raise AuthenticationError(_BAD_CREDENTIALS)

    if not verify_password(user.password_hash, password):
        raise AuthenticationError(_BAD_CREDENTIALS)

    challenge_id, code = await issue_challenge(valkey, principal="staff", subject_id=str(user.id))
    await send_email(
        db,
        to=user.email,
        subject="Your Clear Quote sign-in code",
        html=_OTP_EMAIL_HTML.format(code=code),
    )
    await db.commit()
    return challenge_id


async def verify_otp(
    db: AsyncSession,
    valkey: Redis,
    *,
    challenge_id: str,
    code: str,
) -> User:
    """Verifies the OTP challenge and returns the signed-in `User`."""
    fields = await verify_challenge(valkey, principal="staff", challenge_id=challenge_id, code=code)
    user = await db.get(User, uuid.UUID(fields["subject_id"]))
    if user is None:
        raise AuthenticationError(_BAD_CREDENTIALS)
    return user
