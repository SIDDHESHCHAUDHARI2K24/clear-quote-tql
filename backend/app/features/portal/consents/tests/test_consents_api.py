"""CQ-033 AC1, AC3, AC5, AC6: the borrower consent endpoints on the seeded
Tom & Lisa Brandt persona."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import User
from app.features.borrower.consent.models import Consent, ConsentStatus
from app.features.clients.models import Client
from app.features.notifications.email import service as email_service
from app.features.notifications.outbox.models import OutboxEmail
from app.features.portal.consents.consent_text import HARD_PULL_TEXT_V1
from app.integrations.common.models import IntegrationCall
from conftest import BorrowerSession, StaffSession

MakeBorrower = Callable[..., Awaitable[BorrowerSession]]
MakeStaff = Callable[..., Awaitable[StaffSession]]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    outbox: list[dict[str, str]] = []

    async def _fake_send(*, to: str, subject: str, html: str) -> None:
        outbox.append({"to": to, "subject": subject, "html": html})

    monkeypatch.setattr(email_service, "smtp_send", _fake_send)
    return outbox


async def _seed(db: AsyncSession, *keys: str) -> dict[str, Application]:
    users = await seed_users(db)
    await seed_providers(db)
    personas = {p["key"]: p for p in load_persona_fixtures()}
    seeded: dict[str, Application] = {}
    for key in keys:
        result = await seed_persona(db, personas[key], lo_id=users.lo_ids[0], s3_client=None)
        application = await db.get(Application, result.application_id)
        assert application is not None
        seeded[key] = application
    await db.commit()
    return seeded


async def _client_of(db: AsyncSession, app: Application) -> Client:
    row = await db.get(Client, app.client_id)
    assert row is not None
    return row


async def _request(client: AsyncClient, app: Application) -> str:
    response = await client.post(f"/api/v1/applications/{app.id}/credit/hard-pull-request")
    assert response.status_code == 201, response.text
    return str(response.json()["consent"]["id"])


async def _hard_pull_calls(db: AsyncSession, loan_number: str | None) -> int:
    rows: Sequence[Any] = (
        (await db.execute(select(IntegrationCall.request_summary))).scalars().all()
    )
    return sum(
        1
        for summary in rows
        if isinstance(summary, dict)
        and summary.get("pull_type") == "hard_pull"
        and summary.get("loan_number") == loan_number
    )


async def _events(db: AsyncSession, app: Application, type_: str) -> list[ActivityEvent]:
    return list(
        (
            await db.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == app.id, ActivityEvent.type == type_
                )
            )
        )
        .scalars()
        .all()
    )


def _freeze(monkeypatch: pytest.MonkeyPatch, instant: Any) -> None:
    settings = get_settings().model_copy(update={"clock_now": instant.isoformat()})
    monkeypatch.setattr(clock, "get_settings", lambda: settings)


async def test_hard_pull_consent_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],
) -> None:
    """AC1: LO requests; Brandt reads the text and accepts with his typed
    name; the consent row has the text hash, IP and time; FICO = middle of
    three (690); the LO gets exactly one email."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    sent.clear()

    read = await client.get(f"/api/v1/portal/consents/{consent_id}")

    assert read.status_code == 200, read.text
    body = read.json()
    assert body["status"] == "pending"
    assert body["text"]["version"] == "hard_pull_v1"
    assert body["text"]["body"] == HARD_PULL_TEXT_V1
    for needle in ("Experian", "Equifax", "TransUnion", "hard inquiry"):
        assert needle in body["text"]["body"]
    assert body["borrower_name"] == "Tom Brandt"
    assert body["lo"]["name"]

    wrong = await client.post(
        f"/api/v1/portal/consents/{consent_id}/accept", json={"typed_name": "Lisa Brandt"}
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"]["code"] == "NAME_MISMATCH"

    accepted = await client.post(
        f"/api/v1/portal/consents/{consent_id}/accept",
        json={"typed_name": "  tom   BRANDT "},
        headers={"user-agent": "pytest-browser/1.0"},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["fico_after_pull"] == 690
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None
    assert row.status is ConsentStatus.ACCEPTED
    assert row.text_version == "hard_pull_v1"
    assert row.text_hash == hashlib.sha256(HARD_PULL_TEXT_V1.encode()).hexdigest()
    assert row.typed_name == "tom BRANDT"
    assert row.ip and row.user_agent == "pytest-browser/1.0"
    assert row.at is not None and row.decided_at is not None

    lo = await db_session.get(User, brandt.lo_id)
    assert lo is not None
    assert len(sent) == 1
    assert sent[0]["to"] == lo.email
    assert sent[0]["subject"] == "Credit check authorized — FICO 690"
    outbox = (
        (
            await db_session.execute(
                select(OutboxEmail).where(
                    OutboxEmail.application_id == brandt.id,
                    OutboxEmail.to_email == lo.email,
                )
            )
        )
        .scalars()
        .all()
    )
    assert [o.subject for o in outbox] == ["Credit check authorized — FICO 690"]
    assert len(await _events(db_session, brandt, "credit.consent_accepted")) == 1
    assert len(await _events(db_session, brandt, "credit.hard_pull_completed")) == 1

    # E11: the LO's Credit section shows Authorized with the FICO.
    await make_staff_session(role=UserRole.MANAGER)
    credit = (await client.get(f"/api/v1/applications/{brandt.id}/sections/credit")).json()[
        "credit"
    ]
    assert credit["representative_fico"] == 690
    assert credit["pull_type"] == "hard_pull"
    assert credit["consent"]["status"] == "accepted"
    assert credit["consent"]["fico_after_pull"] == 690


async def test_hard_pull_decline(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],
) -> None:
    """AC3: the reason is stored, the LO is emailed, the Credit section says
    declined, and no pull happens."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    sent.clear()

    declined = await client.post(
        f"/api/v1/portal/consents/{consent_id}/decline",
        json={"reason": "I'd rather wait until next month."},
    )

    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "declined"
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None and row.decline_reason == "I'd rather wait until next month."
    assert row.decided_at is not None
    assert len(sent) == 1 and sent[0]["subject"] == "Credit check declined"
    assert "rather wait" in sent[0]["html"]
    assert await _hard_pull_calls(db_session, brandt.los_loan_guid) == 0
    assert len(await _events(db_session, brandt, "credit.hard_pull_completed")) == 0

    # A declined request cannot then be accepted.
    again = await client.post(
        f"/api/v1/portal/consents/{consent_id}/accept", json={"typed_name": "Tom Brandt"}
    )
    assert again.status_code == 409

    await make_staff_session(role=UserRole.MANAGER)
    credit = (await client.get(f"/api/v1/applications/{brandt.id}/sections/credit")).json()[
        "credit"
    ]
    assert credit["consent"]["status"] == "declined"
    assert credit["consent"]["decline_reason"] == "I'd rather wait until next month."
    assert credit["pull_type"] == "soft_pull"


async def test_consent_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],
) -> None:
    """AC5: another borrower gets 404 on read, accept and decline; an
    unknown id is the same 404."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session()  # a different borrower

    base = f"/api/v1/portal/consents/{consent_id}"
    assert (await client.get(base)).status_code == 404
    assert (
        await client.post(f"{base}/accept", json={"typed_name": "Tom Brandt"})
    ).status_code == 404
    assert (await client.post(f"{base}/decline", json={})).status_code == 404
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/v1/portal/consents/{unknown}")).status_code == 404
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None and row.status is ConsentStatus.PENDING

    client.cookies.clear()
    assert (await client.get(base)).status_code == 401


async def test_consent_expiry(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: 15 days after the request it cannot be accepted, and the row is
    persisted as expired."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    row = await db_session.get(Consent, consent_id)
    assert row is not None and row.requested_at is not None
    _freeze(monkeypatch, row.requested_at + timedelta(days=15))

    accept = await client.post(
        f"/api/v1/portal/consents/{consent_id}/accept", json={"typed_name": "Tom Brandt"}
    )

    assert accept.status_code == 409
    assert accept.json()["error"]["code"] == "CONSENT_EXPIRED"
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None and row.status is ConsentStatus.EXPIRED
    assert (await client.get(f"/api/v1/portal/consents/{consent_id}")).json()["status"] == "expired"
    assert await _hard_pull_calls(db_session, brandt.los_loan_guid) == 0


async def test_consent_expiry_persisted_on_read(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    row = await db_session.get(Consent, consent_id)
    assert row is not None and row.requested_at is not None

    _freeze(monkeypatch, row.requested_at + timedelta(days=13))
    assert (await client.get(f"/api/v1/portal/consents/{consent_id}")).json()["status"] == "pending"
    _freeze(monkeypatch, row.requested_at + timedelta(days=15))
    assert (await client.get(f"/api/v1/portal/consents/{consent_id}")).json()["status"] == "expired"
    row = await db_session.get(Consent, consent_id, populate_existing=True)
    assert row is not None and row.status is ConsentStatus.EXPIRED
    decline = await client.post(f"/api/v1/portal/consents/{consent_id}/decline", json={})
    assert decline.status_code == 409


async def test_consent_accept_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    make_borrower_session: MakeBorrower,
    sent: list[dict[str, str]],
) -> None:
    """AC6: accepting twice pulls once and emails the LO once."""
    brandt = (await _seed(db_session, "tom_lisa_brandt"))["tom_lisa_brandt"]
    await make_staff_session(role=UserRole.MANAGER)
    consent_id = await _request(client, brandt)
    await make_borrower_session(client_row=await _client_of(db_session, brandt))
    sent.clear()
    url = f"/api/v1/portal/consents/{consent_id}/accept"

    first = await client.post(url, json={"typed_name": "Tom Brandt"})
    second = await client.post(url, json={"typed_name": "Tom Brandt"})

    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["status"] == "accepted"
    assert second.json()["fico_after_pull"] == 690
    assert await _hard_pull_calls(db_session, brandt.los_loan_guid) == 1
    assert len(await _events(db_session, brandt, "credit.hard_pull_completed")) == 1
    assert len(sent) == 1
    count = (
        await db_session.execute(
            select(func.count()).select_from(Consent).where(Consent.application_id == brandt.id)
        )
    ).scalar_one()
    assert count == 1
