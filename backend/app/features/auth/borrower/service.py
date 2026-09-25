"""Borrower self-service sign-up + login, both gated by an email OTP.

Reuses CQ-014's principal-agnostic `auth/otp`, `auth/otp/rate_limit` and
`auth/sessions` modules with `principal="borrower"` (plan.md Decision #3),
plus `core/security`, `notifications/email/service.send_email` and
`auth/users/service.normalize_email`. Nothing here is copy-pasted from
`auth/staff/service.py`; only the shape (rate limit -> check -> OTP issue
+ email, and verify -> signed-in row) matches it.

Pending sign-up (Decision #4): `signup` never writes `borrower_accounts` or
`clients` rows. It hashes the password immediately and carries
`{full_name, email, password_hash, mode="signup"}` through the OTP
challenge's `extra`; the account (and, if needed, a new client) are only
created when `verify_otp` succeeds. Login challenges instead carry
`mode="login"` with `subject_id` = the existing account's id.
"""

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, ConflictError, ValidationAppError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_token,
    hash_password_async,
    verify_password_async,
)
from app.features.applications.assignment import least_loaded_lo_id as _least_loaded_lo_id
from app.features.applications.models import Application
from app.features.auth.borrower.schemas import BorrowerMeOut, LatestApplicationOut
from app.features.auth.models import BorrowerAccount
from app.features.auth.otp.rate_limit import check_login, check_signup
from app.features.auth.otp.service import issue_challenge, verify_challenge
from app.features.auth.users.service import MIN_PASSWORD_LENGTH, normalize_email
from app.features.clients.models import Client
from app.features.notifications.email.service import send_email

_BAD_CREDENTIALS = "Invalid email or password"
_INVALID_OR_EXPIRED = "Invalid or expired code"

_OTP_SUBJECT = "Your Clear Quote sign-in code"
_OTP_EMAIL_HTML = (
    "<p>Your Clear Quote sign-in code is <strong>{code}</strong>.</p>"
    "<p>This code expires in 5 minutes.</p>"
)
_EXISTING_ACCOUNT_SUBJECT = "You already have a Clear Quote account"
_EXISTING_ACCOUNT_HTML = (
    "<p>You already have a Clear Quote account for {email}.</p>"
    "<p>Sign in instead from the Clear Quote borrower portal.</p>"
)


async def signup(
    db: AsyncSession,
    valkey: Redis,
    *,
    full_name: str,
    email: str,
    password: str,
    ip: str,
) -> str:
    """Starts a sign-up: rate-limits, then either emails a real OTP
    challenge (new email) or the "you already have an account" notice
    (existing email) — the caller gets an indistinguishable 200 +
    `challenge_id` either way (Decision #5). No `borrower_accounts` or
    `clients` row is written until `verify_otp` succeeds.

    Raises `RateLimitedError` (over the sign-up rate limit) or
    `ValidationAppError` (password shorter than `MIN_PASSWORD_LENGTH`).
    The rate limit is checked first (mirroring `staff/service.py::login`)
    so repeated invalid-password attempts still count against it.

    Uses `check_signup`'s own counters (Decision #8, revised), separate
    from `login`'s, so a flood of sign-ups for someone's email can't lock
    them out of logging in.
    """
    normalized_email = normalize_email(email)
    await check_signup(valkey, principal="borrower", email=normalized_email, ip=ip)

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationAppError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    existing = (
        await db.execute(select(BorrowerAccount).where(BorrowerAccount.email == normalized_email))
    ).scalar_one_or_none()

    if existing is not None:
        # Decision #5: same response shape as a fresh sign-up, but the
        # *returned* challenge id is never stored in Valkey, so
        # `verify_otp` always fails it with the generic "Invalid or
        # expired code" — and the email tells the owner to sign in
        # instead, with no code.
        #
        # `hash_password_async` and `issue_challenge` still run here (their
        # results discarded, the issued challenge simply expiring unused
        # via its TTL) so this branch pays the same argon2 CPU time and
        # Valkey round trip as the new-email branch below — otherwise an
        # attacker could distinguish "existing account" from "new
        # account" purely by response latency, which is exactly what the
        # identical-response design is meant to hide.
        await hash_password_async(password)
        await issue_challenge(
            valkey, principal="borrower", subject_id="", extra={"mode": "signup_noop"}
        )
        await send_email(
            db,
            to=normalized_email,
            subject=_EXISTING_ACCOUNT_SUBJECT,
            html=_EXISTING_ACCOUNT_HTML.format(email=normalized_email),
        )
        await db.commit()
        return generate_token(24)

    password_hash = await hash_password_async(password)
    challenge_id, code = await issue_challenge(
        valkey,
        principal="borrower",
        subject_id="",
        extra={
            "mode": "signup",
            "full_name": full_name,
            "email": normalized_email,
            "password_hash": password_hash,
        },
    )
    await send_email(
        db,
        to=normalized_email,
        subject=_OTP_SUBJECT,
        html=_OTP_EMAIL_HTML.format(code=code),
    )
    await db.commit()
    return challenge_id


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

    An unknown email, an account with no `password_hash` set (never
    completed sign-up), and a wrong password all raise the identical
    `AuthenticationError` — the first two also run a dummy argon2 verify so
    timing doesn't reveal which case applies.
    """
    normalized_email = normalize_email(email)
    await check_login(valkey, principal="borrower", email=normalized_email, ip=ip)

    account = (
        await db.execute(select(BorrowerAccount).where(BorrowerAccount.email == normalized_email))
    ).scalar_one_or_none()

    if account is None or account.password_hash is None:
        await verify_password_async(DUMMY_PASSWORD_HASH, password)
        raise AuthenticationError(_BAD_CREDENTIALS)

    if not await verify_password_async(account.password_hash, password):
        raise AuthenticationError(_BAD_CREDENTIALS)

    challenge_id, code = await issue_challenge(
        valkey,
        principal="borrower",
        subject_id=str(account.id),
        extra={"mode": "login"},
    )
    await send_email(
        db,
        to=account.email,
        subject=_OTP_SUBJECT,
        html=_OTP_EMAIL_HTML.format(code=code),
    )
    await db.commit()
    return challenge_id


async def _find_or_create_client(db: AsyncSession, *, full_name: str, email: str) -> Client:
    """Matches an existing client by case-insensitive email (Decision #6,
    oldest by `created_at` then `id` if more than one), otherwise creates
    one assigned to the least-loaded LO (Decision #7, superseded by P5/P6
    E15: `applications.assignment.least_loaded_lo_id` -- fewest active
    applications, ties alphabetical by name).

    Raises `ConflictError` (`code="NO_LOAN_OFFICER"`) if there is no LO to
    assign a brand-new client to.
    """
    client = (
        (
            await db.execute(
                select(Client)
                .where(func.lower(Client.email) == email)
                .order_by(Client.created_at, Client.id)
            )
        )
        .scalars()
        .first()
    )
    if client is not None:
        return client

    lo_id = await _least_loaded_lo_id(db)
    if lo_id is None:
        raise ConflictError(
            "No loan officer is available to assign this client to.", code="NO_LOAN_OFFICER"
        )

    client = Client(full_name=full_name, email=email, assigned_lo_id=lo_id)
    db.add(client)
    await db.flush()
    return client


async def verify_otp(
    db: AsyncSession,
    valkey: Redis,
    *,
    challenge_id: str,
    code: str,
) -> BorrowerAccount:
    """Verifies the OTP challenge and returns the signed-in
    `BorrowerAccount`, creating it (and, if needed, its `Client`) for
    `mode="signup"` challenges.

    Guards the race where another request created the account for this
    email between `signup` and this call: the insert runs in a SAVEPOINT
    (mirroring `users/service.py::create_user`), and a losing
    `IntegrityError` becomes the generic "Invalid or expired code" 401
    rather than a raw database error.
    """
    fields = await verify_challenge(
        valkey, principal="borrower", challenge_id=challenge_id, code=code
    )
    mode = fields.get("mode")
    now = datetime.now(UTC)

    if mode == "signup":
        full_name = fields["full_name"]
        email = fields["email"]
        password_hash = fields["password_hash"]

        client = await _find_or_create_client(db, full_name=full_name, email=email)
        account = BorrowerAccount(
            client_id=client.id,
            email=email,
            password_hash=password_hash,
            email_verified_at=now,
            last_login_at=now,
        )
        try:
            async with db.begin_nested():
                db.add(account)
                await db.flush()
        except IntegrityError as exc:
            raise AuthenticationError(_INVALID_OR_EXPIRED) from exc
        await db.commit()
        return account

    if mode == "login":
        login_account = await db.get(BorrowerAccount, uuid.UUID(fields["subject_id"]))
        if login_account is None:
            raise AuthenticationError(_BAD_CREDENTIALS)
        login_account.last_login_at = now
        await db.commit()
        return login_account

    raise AuthenticationError(_INVALID_OR_EXPIRED)


async def build_me(db: AsyncSession, account: BorrowerAccount) -> BorrowerMeOut:
    """Builds the `/me` response (Decision #10): the account, its client,
    and the latest application's id + status (or `None`)."""
    client = await db.get(Client, account.client_id)
    assert client is not None  # borrower_accounts.client_id is NOT NULL + FK-enforced

    latest_application = (
        await db.execute(
            select(Application)
            .where(Application.client_id == account.client_id)
            .order_by(Application.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return BorrowerMeOut(
        account_id=account.id,
        email=account.email,
        client_id=account.client_id,
        full_name=client.full_name,
        first_name=client.full_name.split()[0] if client.full_name.strip() else "",
        latest_application=(
            LatestApplicationOut(id=latest_application.id, status=latest_application.status.value)
            if latest_application is not None
            else None
        ),
    )
