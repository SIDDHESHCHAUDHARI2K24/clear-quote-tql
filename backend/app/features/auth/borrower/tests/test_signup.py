"""AC1-AC3: borrower self sign-up -> OTP email -> verify -> account (+
client) created, linking an existing client, creating a new one for the
least-loaded LO, and being indistinguishable for an already-registered
email.

`capture_smtp` mirrors `auth/staff/tests/test_login_flow.py`'s seam so
these tests never touch a live SMTP server.
"""

import re
import uuid

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.security import hash_password
from app.features.auth.models import BorrowerAccount, User
from app.features.clients.models import Client
from app.features.notifications.email import service as email_service

PASSWORD = "Test!2345"

_CODE_RE = re.compile(r"\b(\d{6})\b")


@pytest.fixture(autouse=True)
def capture_smtp(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []

    async def _fake_smtp_send(*, to: str, subject: str, html: str) -> None:
        calls.append({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr(email_service, "smtp_send", _fake_smtp_send)
    return calls


async def _make_lo(db_session: AsyncSession, *, email: str | None = None) -> User:
    lo = User(
        email=email or f"lo-{uuid.uuid4()}@clearquote.test",
        password_hash="x",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()
    return lo


async def _make_client(db_session: AsyncSession, *, lo: User, email: str) -> Client:
    client = Client(full_name="Existing Client", email=email, assigned_lo_id=lo.id)
    db_session.add(client)
    await db_session.flush()
    return client


def _extract_code(calls: list[dict[str, str]]) -> str:
    match = _CODE_RE.search(calls[-1]["html"])
    assert match is not None
    return match.group(1)


async def test_signup_links_existing_client(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    lo = await _make_lo(db_session)
    existing_client = await _make_client(db_session, lo=lo, email="linked@clearquote.test")

    signup_response = await client.post(
        "/api/v1/auth/borrower/signup",
        json={"full_name": "New Borrower", "email": "linked@clearquote.test", "password": PASSWORD},
    )
    assert signup_response.status_code == 200
    challenge_id = signup_response.json()["challenge_id"]
    code = _extract_code(capture_smtp)

    verify_response = await client.post(
        "/api/v1/auth/borrower/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["client_id"] == str(existing_client.id)

    clients = (await db_session.execute(select(Client))).scalars().all()
    assert len(clients) == 1

    me_response = await client.get("/api/v1/auth/borrower/me")
    assert me_response.status_code == 200
    assert me_response.json()["client_id"] == str(existing_client.id)


async def test_signup_unknown_email_creates_client_for_least_loaded_lo(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    busy_lo = await _make_lo(db_session)
    quiet_lo = await _make_lo(db_session)
    # `busy_lo` has two clients already, `quiet_lo` has none — the new
    # client must go to `quiet_lo`.
    await _make_client(db_session, lo=busy_lo, email="busy1@clearquote.test")
    await _make_client(db_session, lo=busy_lo, email="busy2@clearquote.test")

    signup_response = await client.post(
        "/api/v1/auth/borrower/signup",
        json={
            "full_name": "Brand New Borrower",
            "email": "unknown@clearquote.test",
            "password": PASSWORD,
        },
    )
    assert signup_response.status_code == 200
    challenge_id = signup_response.json()["challenge_id"]
    code = _extract_code(capture_smtp)

    verify_response = await client.post(
        "/api/v1/auth/borrower/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert verify_response.status_code == 200
    new_client_id = uuid.UUID(verify_response.json()["client_id"])

    new_client = await db_session.get(Client, new_client_id)
    assert new_client is not None
    assert new_client.assigned_lo_id == quiet_lo.id
    assert new_client.email == "unknown@clearquote.test"
    assert new_client.full_name == "Brand New Borrower"


async def test_signup_existing_account_is_indistinguishable(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    lo = await _make_lo(db_session)
    existing_client = await _make_client(db_session, lo=lo, email="hasaccount@clearquote.test")
    db_session.add(
        BorrowerAccount(
            client_id=existing_client.id,
            email="hasaccount@clearquote.test",
            password_hash=hash_password(PASSWORD),
        )
    )
    await db_session.flush()

    fresh_signup = await client.post(
        "/api/v1/auth/borrower/signup",
        json={
            "full_name": "Someone Else",
            "email": "neverseen@clearquote.test",
            "password": PASSWORD,
        },
    )
    existing_signup = await client.post(
        "/api/v1/auth/borrower/signup",
        json={
            "full_name": "Someone Else",
            "email": "hasaccount@clearquote.test",
            "password": PASSWORD,
        },
    )

    assert fresh_signup.status_code == existing_signup.status_code == 200
    assert set(fresh_signup.json().keys()) == set(existing_signup.json().keys()) == {"challenge_id"}

    # The email sent for the existing account says so and carries no code.
    assert "already" in capture_smtp[-1]["subject"].lower()
    assert _CODE_RE.search(capture_smtp[-1]["html"]) is None

    # No second account was created, and verifying the existing-account
    # challenge fails (it was never actually stored).
    accounts = (
        (
            await db_session.execute(
                select(BorrowerAccount).where(BorrowerAccount.email == "hasaccount@clearquote.test")
            )
        )
        .scalars()
        .all()
    )
    assert len(accounts) == 1

    verify_response = await client.post(
        "/api/v1/auth/borrower/otp/verify",
        json={"challenge_id": existing_signup.json()["challenge_id"], "code": "000000"},
    )
    assert verify_response.status_code == 401


async def test_signup_existing_account_still_hashes_password(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timing-safety regression: the existing-account branch of `signup`
    must pay the same argon2 cost as the new-email branch (mirroring
    `login`'s dummy verify for an unknown email) — otherwise an attacker
    can distinguish "existing account" from "new account" purely by
    response latency, defeating Decision #5's identical-response design.
    """
    from app.features.auth.borrower import service as borrower_service

    lo = await _make_lo(db_session)
    existing_client = await _make_client(db_session, lo=lo, email="timing@clearquote.test")
    db_session.add(
        BorrowerAccount(
            client_id=existing_client.id,
            email="timing@clearquote.test",
            password_hash=hash_password(PASSWORD),
        )
    )
    await db_session.flush()

    calls: list[str] = []
    original_hash_password_async = borrower_service.hash_password_async

    async def _tracking_hash_password_async(password: str) -> str:
        calls.append(password)
        return await original_hash_password_async(password)

    monkeypatch.setattr(borrower_service, "hash_password_async", _tracking_hash_password_async)

    response = await client.post(
        "/api/v1/auth/borrower/signup",
        json={"full_name": "Timing Check", "email": "timing@clearquote.test", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert calls == [PASSWORD]


async def test_signup_weak_password_rejected(client: AsyncClient) -> None:
    """`BorrowerSignupRequest.password` carries `min_length=MIN_PASSWORD_LENGTH`
    (plan.md fix 3), so a short password is now rejected by pydantic before
    `borrower/service.py::signup` ever runs — a plain FastAPI validation
    body (`{"detail": [...]}`), not the service's `ValidationAppError` shape
    (`{"error": {...}}`)."""
    response = await client.post(
        "/api/v1/auth/borrower/signup",
        json={"full_name": "Weak Password", "email": "weak@clearquote.test", "password": "short1"},
    )
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert "error" not in body


async def test_signup_oversized_full_name_rejected(client: AsyncClient) -> None:
    """A `full_name` far past the 1-200 (post-strip) rule must be rejected
    by pydantic's raw `Field(max_length=...)` before
    `_strip_and_bound_full_name` ever runs `.strip()` on it."""
    response = await client.post(
        "/api/v1/auth/borrower/signup",
        json={
            "full_name": "x" * 10_000,
            "email": "huge-name@clearquote.test",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 422


async def test_signup_service_still_rejects_short_password(
    db_session: AsyncSession, valkey: Redis
) -> None:
    """Defense in depth (plan.md fix 3): `borrower/service.py::signup`
    keeps its own length check for any caller that bypasses
    `BorrowerSignupRequest`'s schema-level `min_length`."""
    from app.core.errors import ValidationAppError
    from app.features.auth.borrower import service as borrower_service

    with pytest.raises(ValidationAppError):
        await borrower_service.signup(
            db_session,
            valkey,
            full_name="Weak Password",
            email="weak-direct@clearquote.test",
            password="short1",
            ip="127.0.0.1",
        )


async def test_signup_verify_wrong_code_fails(
    client: AsyncClient, capture_smtp: list[dict[str, str]]
) -> None:
    signup_response = await client.post(
        "/api/v1/auth/borrower/signup",
        json={
            "full_name": "Wrong Code",
            "email": "wrongcode@clearquote.test",
            "password": PASSWORD,
        },
    )
    challenge_id = signup_response.json()["challenge_id"]

    verify_response = await client.post(
        "/api/v1/auth/borrower/otp/verify", json={"challenge_id": challenge_id, "code": "000000"}
    )
    assert verify_response.status_code == 401


async def test_signup_rate_limit_is_separate_from_login(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    """Decision #8 (revised): a flood of sign-ups for an email must not
    trip that email's login rate limit — they use separate Valkey
    counters. Login for the account first has to exist, so it's created
    directly rather than through `/signup` (which would itself consume a
    sign-up-counter slot per call)."""
    lo = await _make_lo(db_session)
    existing_client = await _make_client(
        db_session, lo=lo, email="ratelimit-signup@clearquote.test"
    )
    db_session.add(
        BorrowerAccount(
            client_id=existing_client.id,
            email="ratelimit-signup@clearquote.test",
            password_hash=hash_password(PASSWORD),
        )
    )
    await db_session.flush()

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/borrower/signup",
            json={
                "full_name": "Flooder",
                "email": "ratelimit-signup@clearquote.test",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 200

    # Login for the same email is unaffected by the sign-up flood.
    login_response = await client.post(
        "/api/v1/auth/borrower/login",
        json={"email": "ratelimit-signup@clearquote.test", "password": PASSWORD},
    )
    assert login_response.status_code == 200

    # The 6th sign-up trips the sign-up-specific limit.
    sixth_signup = await client.post(
        "/api/v1/auth/borrower/signup",
        json={
            "full_name": "Flooder",
            "email": "ratelimit-signup@clearquote.test",
            "password": PASSWORD,
        },
    )
    assert sixth_signup.status_code == 429
    assert sixth_signup.json()["error"]["code"] == "RATE_LIMITED"


async def test_signup_verify_with_no_lo_returns_409(
    client: AsyncClient, capture_smtp: list[dict[str, str]]
) -> None:
    """No LO exists at all — the account is never created and the new
    client can't be assigned."""
    signup_response = await client.post(
        "/api/v1/auth/borrower/signup",
        json={"full_name": "No LO Around", "email": "nolo@clearquote.test", "password": PASSWORD},
    )
    challenge_id = signup_response.json()["challenge_id"]
    code = _extract_code(capture_smtp)

    verify_response = await client.post(
        "/api/v1/auth/borrower/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert verify_response.status_code == 409
    assert verify_response.json()["error"]["code"] == "NO_LOAN_OFFICER"
