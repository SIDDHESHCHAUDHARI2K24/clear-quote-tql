"""AC1-AC5: staff login -> OTP email -> verify -> session cookie -> logout.

`capture_smtp` monkeypatches `email/service.py`'s `smtp_send` seam so these
API tests never touch a live SMTP server; users are created directly with
`hash_password` (not via CQ-014 T4's `auth/users` service, which this task
doesn't own).
"""

import re

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.security import hash_password
from app.features.auth.models import User
from app.features.notifications.email import service as email_service
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail

PASSWORD = "Test!2345"

_CODE_RE = re.compile(r"\b(\d{6})\b")


async def _make_staff_user(db_session: AsyncSession, *, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture(autouse=True)
def capture_smtp(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []

    async def _fake_smtp_send(*, to: str, subject: str, html: str) -> None:
        calls.append({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr(email_service, "smtp_send", _fake_smtp_send)
    return calls


async def test_login_sends_otp_email(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    user = await _make_staff_user(db_session, email="lo-otp@clearquote.test")

    response = await client.post(
        "/api/v1/auth/staff/login", json={"email": user.email, "password": PASSWORD}
    )

    assert response.status_code == 200
    assert "challenge_id" in response.json()

    assert len(capture_smtp) == 1
    assert capture_smtp[0]["to"] == user.email
    assert _CODE_RE.search(capture_smtp[0]["html"]) is not None

    row = (
        await db_session.execute(select(OutboxEmail).where(OutboxEmail.to_email == user.email))
    ).scalar_one()
    assert row.status == EmailStatus.SENT


async def test_bad_credentials_same_401(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _make_staff_user(db_session, email="lo-bad@clearquote.test")

    unknown_response = await client.post(
        "/api/v1/auth/staff/login",
        json={"email": "nobody@clearquote.test", "password": "whatever"},
    )
    wrong_password_response = await client.post(
        "/api/v1/auth/staff/login",
        json={"email": user.email, "password": "wrong-password"},
    )

    assert unknown_response.status_code == 401
    assert wrong_password_response.status_code == 401
    assert unknown_response.json() == wrong_password_response.json()


async def test_login_rate_limited(client: AsyncClient) -> None:
    email = "lo-rate-limited@clearquote.test"

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/staff/login", json={"email": email, "password": "whatever"}
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/v1/auth/staff/login", json={"email": email, "password": "whatever"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


async def test_login_rate_limit_is_case_and_whitespace_insensitive(client: AsyncClient) -> None:
    """`normalize_email` runs before the rate-limit key is built, so
    `"LO@X"` and `" lo@x "` count toward the same per-email counter as
    `"lo@x"` instead of each getting their own limit."""
    email_variants = [
        "lo-normalize@clearquote.test",
        "LO-NORMALIZE@clearquote.test",
        " lo-normalize@clearquote.test ",
        "Lo-Normalize@ClearQuote.test",
        "lo-normalize@clearquote.test",
    ]

    for email in email_variants:
        response = await client.post(
            "/api/v1/auth/staff/login", json={"email": email, "password": "whatever"}
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/v1/auth/staff/login",
        json={"email": "lo-normalize@clearquote.test", "password": "whatever"},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


async def test_login_rejects_oversized_password(client: AsyncClient) -> None:
    """A password over `StaffLoginRequest`'s `max_length` is rejected by
    pydantic (422) before it ever reaches argon2 — an oversized password
    would otherwise cost disproportionate CPU to hash/verify."""
    response = await client.post(
        "/api/v1/auth/staff/login",
        json={"email": "lo-oversized@clearquote.test", "password": "x" * 257},
    )
    assert response.status_code == 422


async def test_verify_rejects_oversized_fields(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/staff/otp/verify",
        json={"challenge_id": "c" * 65, "code": "1234567"},
    )
    assert response.status_code == 422


async def test_cookie_flags_me_logout(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    user = await _make_staff_user(db_session, email="lo-cookie@clearquote.test")

    login_response = await client.post(
        "/api/v1/auth/staff/login", json={"email": user.email, "password": PASSWORD}
    )
    challenge_id = login_response.json()["challenge_id"]
    code_match = _CODE_RE.search(capture_smtp[-1]["html"])
    assert code_match is not None
    code = code_match.group(1)

    verify_response = await client.post(
        "/api/v1/auth/staff/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["email"] == user.email

    set_cookie = verify_response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "path=/" in set_cookie.lower()

    me_response = await client.get("/api/v1/auth/staff/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == user.email

    logout_response = await client.post("/api/v1/auth/staff/logout")
    assert logout_response.status_code == 204

    me_after_logout = await client.get("/api/v1/auth/staff/me")
    assert me_after_logout.status_code == 401


async def test_verify_wrong_code_401(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    user = await _make_staff_user(db_session, email="lo-wrong-code@clearquote.test")

    login_response = await client.post(
        "/api/v1/auth/staff/login", json={"email": user.email, "password": PASSWORD}
    )
    challenge_id = login_response.json()["challenge_id"]

    verify_response = await client.post(
        "/api/v1/auth/staff/otp/verify",
        json={"challenge_id": challenge_id, "code": "000000"},
    )
    assert verify_response.status_code == 401


async def test_logout_without_session_still_succeeds(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/staff/logout")
    assert response.status_code == 204


async def test_me_without_session_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/staff/me")
    assert response.status_code == 401
