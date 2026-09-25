"""AC4-AC5: borrower login -> OTP -> session cookie, its error/rate-limit
shapes, and that a borrower cookie never authenticates a staff endpoint (or
vice versa)."""

import re
import uuid

import pytest
from httpx import AsyncClient
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


async def _make_account(
    db_session: AsyncSession, *, email: str, password: str | None = PASSWORD
) -> tuple[User, BorrowerAccount]:
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote.test",
        password_hash="x",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()

    borrower_client = Client(full_name="Test Borrower", email=email, assigned_lo_id=lo.id)
    db_session.add(borrower_client)
    await db_session.flush()

    account = BorrowerAccount(
        client_id=borrower_client.id,
        email=email,
        password_hash=hash_password(password) if password is not None else None,
    )
    db_session.add(account)
    await db_session.flush()
    return lo, account


def _extract_code(calls: list[dict[str, str]]) -> str:
    match = _CODE_RE.search(calls[-1]["html"])
    assert match is not None
    return match.group(1)


async def test_login_happy_path_cookie_flags_and_me(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    _, account = await _make_account(db_session, email="login-happy@clearquote.test")

    login_response = await client.post(
        "/api/v1/auth/borrower/login", json={"email": account.email, "password": PASSWORD}
    )
    assert login_response.status_code == 200
    challenge_id = login_response.json()["challenge_id"]
    code = _extract_code(capture_smtp)

    verify_response = await client.post(
        "/api/v1/auth/borrower/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["email"] == account.email

    set_cookie = verify_response.headers["set-cookie"]
    assert "cq_borrower_session" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "path=/" in set_cookie.lower()
    assert "max-age=604800" in set_cookie.lower()

    me_response = await client.get("/api/v1/auth/borrower/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == account.email


async def test_login_unknown_email_and_wrong_password_same_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, account = await _make_account(db_session, email="login-bad@clearquote.test")

    unknown_response = await client.post(
        "/api/v1/auth/borrower/login",
        json={"email": "nobody@clearquote.test", "password": "whatever"},
    )
    wrong_password_response = await client.post(
        "/api/v1/auth/borrower/login",
        json={"email": account.email, "password": "wrong-password"},
    )

    assert unknown_response.status_code == 401
    assert wrong_password_response.status_code == 401
    assert unknown_response.json() == wrong_password_response.json()


async def test_login_account_without_password_gets_same_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An account that never completed sign-up (`password_hash IS NULL`)
    gets the same generic 401 as an unknown email."""
    _, account = await _make_account(
        db_session, email="login-nopass@clearquote.test", password=None
    )

    response = await client.post(
        "/api/v1/auth/borrower/login", json={"email": account.email, "password": "whatever"}
    )
    assert response.status_code == 401


async def test_login_otp_attempts_exhausted(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    _, account = await _make_account(db_session, email="login-attempts@clearquote.test")

    login_response = await client.post(
        "/api/v1/auth/borrower/login", json={"email": account.email, "password": PASSWORD}
    )
    challenge_id = login_response.json()["challenge_id"]
    code = _extract_code(capture_smtp)

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/borrower/otp/verify",
            json={"challenge_id": challenge_id, "code": "000000"},
        )
        assert response.status_code == 401

    # The challenge is spent even with the right code now.
    final_response = await client.post(
        "/api/v1/auth/borrower/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert final_response.status_code == 401


async def test_login_rate_limited(client: AsyncClient) -> None:
    email = "login-rate-limited@clearquote.test"

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/borrower/login", json={"email": email, "password": "whatever"}
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/v1/auth/borrower/login", json={"email": email, "password": "whatever"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


async def test_cookies_do_not_cross_principals(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    staff_user = User(
        email="staff-cross@clearquote.test",
        password_hash=hash_password(PASSWORD),
        role=UserRole.LO,
        full_name="Staff Cross",
    )
    db_session.add(staff_user)
    await db_session.flush()
    _, borrower_account = await _make_account(db_session, email="borrower-cross@clearquote.test")

    staff_login = await client.post(
        "/api/v1/auth/staff/login", json={"email": staff_user.email, "password": PASSWORD}
    )
    staff_challenge = staff_login.json()["challenge_id"]
    staff_code = _extract_code(capture_smtp)
    await client.post(
        "/api/v1/auth/staff/otp/verify", json={"challenge_id": staff_challenge, "code": staff_code}
    )

    # The staff cookie is now set on `client`; a borrower `/me` must reject it.
    borrower_me_with_staff_cookie = await client.get("/api/v1/auth/borrower/me")
    assert borrower_me_with_staff_cookie.status_code == 401

    # Drop the staff cookie so only the borrower cookie is present below —
    # otherwise both would ride along on every request and a passing staff
    # `/me` wouldn't prove the borrower cookie alone was rejected.
    client.cookies.delete("cq_staff_session")

    borrower_login = await client.post(
        "/api/v1/auth/borrower/login",
        json={"email": borrower_account.email, "password": PASSWORD},
    )
    borrower_challenge = borrower_login.json()["challenge_id"]
    borrower_code = _extract_code(capture_smtp)
    await client.post(
        "/api/v1/auth/borrower/otp/verify",
        json={"challenge_id": borrower_challenge, "code": borrower_code},
    )

    # Only the borrower cookie is present now; staff `/me` must reject it.
    staff_me_with_borrower_cookie = await client.get("/api/v1/auth/staff/me")
    assert staff_me_with_borrower_cookie.status_code == 401

    borrower_me_with_borrower_cookie = await client.get("/api/v1/auth/borrower/me")
    assert borrower_me_with_borrower_cookie.status_code == 200
    assert borrower_me_with_borrower_cookie.json()["email"] == borrower_account.email


async def test_logout_then_me_401(
    client: AsyncClient, db_session: AsyncSession, capture_smtp: list[dict[str, str]]
) -> None:
    _, account = await _make_account(db_session, email="logout-borrower@clearquote.test")

    login_response = await client.post(
        "/api/v1/auth/borrower/login", json={"email": account.email, "password": PASSWORD}
    )
    challenge_id = login_response.json()["challenge_id"]
    code = _extract_code(capture_smtp)
    await client.post(
        "/api/v1/auth/borrower/otp/verify", json={"challenge_id": challenge_id, "code": code}
    )

    logout_response = await client.post("/api/v1/auth/borrower/logout")
    assert logout_response.status_code == 204

    me_response = await client.get("/api/v1/auth/borrower/me")
    assert me_response.status_code == 401


async def test_me_without_session_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/borrower/me")
    assert response.status_code == 401
