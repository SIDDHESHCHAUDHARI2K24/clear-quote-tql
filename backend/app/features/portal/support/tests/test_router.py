"""`POST /api/v1/portal/support` (CQ-034 spec.md AC1-AC5)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.clients.models import Client
from app.features.notifications.outbox.models import OutboxEmail
from conftest import BorrowerSession

MakeBorrowerSession = Callable[..., Awaitable[BorrowerSession]]
MakeApplication = Callable[..., Awaitable[Application]]

_VALID_BODY = {
    "topic": "quote",
    "message": "I have a question about the buydown option on my quote.",
    "preferred_contact": "email",
}


async def _sign_in(
    db_session: AsyncSession, make_borrower_session: MakeBorrowerSession, application: Application
) -> Client:
    client_row = await db_session.get(Client, application.client_id)
    assert client_row is not None
    await make_borrower_session(client_row)
    return client_row


async def test_support_request_emails(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: MakeApplication,
) -> None:
    """AC1/AC2: one inbox email with the borrower's context and the
    application's stage/status/property, one confirmation email with the
    same reference, one outbox row per email, one activity event."""
    application = await make_application(first_name="Marcus", last_name="Hale")
    client_row = await _sign_in(db_session, make_borrower_session, application)

    response = await client.post("/api/v1/portal/support", json=_VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    reference = body["reference"]
    assert reference.startswith("SUP-")
    assert len(reference) == 9  # "SUP-" + 5 chars
    assert body["lo"]["name"]

    emails = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(emails) == 2

    inbox_email = next(e for e in emails if e.to_email != client_row.email)
    confirmation_email = next(e for e in emails if e.to_email == client_row.email)

    assert reference in inbox_email.subject
    assert "quote" in inbox_email.subject
    assert "Marcus Hale" in inbox_email.subject
    assert client_row.full_name in inbox_email.html
    assert client_row.email in inbox_email.html
    assert _VALID_BODY["message"] in inbox_email.html
    assert str(application.id) in inbox_email.html

    assert reference in confirmation_email.subject
    assert reference in confirmation_email.html

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "support.requested",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, dict)
    assert payload["reference"] == reference


async def test_support_validation_short_message(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: MakeApplication,
) -> None:
    """AC3: a 9-character message is rejected with a field error."""
    application = await make_application()
    await _sign_in(db_session, make_borrower_session, application)

    short_message = "too short"
    assert len(short_message) == 9

    response = await client.post(
        "/api/v1/portal/support",
        json={"topic": "quote", "message": short_message, "preferred_contact": "email"},
    )

    assert response.status_code == 422


async def test_support_validation_phone_required_when_preferred(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: MakeApplication,
) -> None:
    """AC3: `preferred_contact=phone` with no phone is rejected."""
    application = await make_application()
    await _sign_in(db_session, make_borrower_session, application)

    response = await client.post(
        "/api/v1/portal/support",
        json={**_VALID_BODY, "preferred_contact": "phone"},
    )

    assert response.status_code == 422


async def test_support_validation_phone_accepted_with_phone(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: MakeApplication,
) -> None:
    application = await make_application()
    await _sign_in(db_session, make_borrower_session, application)

    response = await client.post(
        "/api/v1/portal/support",
        json={**_VALID_BODY, "preferred_contact": "phone", "phone": "8135550123"},
    )

    assert response.status_code == 200


async def test_support_rate_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    valkey: Redis,
    make_borrower_session: MakeBorrowerSession,
    make_application: MakeApplication,
) -> None:
    """AC4: the 6th request in an hour returns 429 with the exact wording
    the frontend matches on."""
    application = await make_application()
    await _sign_in(db_session, make_borrower_session, application)

    for _ in range(5):
        response = await client.post("/api/v1/portal/support", json=_VALID_BODY)
        assert response.status_code == 200

    response = await client.post("/api/v1/portal/support", json=_VALID_BODY)
    assert response.status_code == 429
    assert response.json()["error"]["message"] == "Please try again later"


async def test_support_without_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
) -> None:
    """AC5: a borrower with no application can still submit; the inbox
    email says "No application yet" and no activity event is written
    (there's no application to attach it to)."""
    session = await make_borrower_session()

    response = await client.post("/api/v1/portal/support", json=_VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    reference = body["reference"]

    emails = (
        (await db_session.execute(select(OutboxEmail).where(OutboxEmail.application_id.is_(None))))
        .scalars()
        .all()
    )
    assert len(emails) == 2
    inbox_email = next(e for e in emails if e.to_email != session.client.email)
    assert "No application yet" in inbox_email.html

    events = (await db_session.execute(select(ActivityEvent))).scalars().all()
    assert events == []
    assert reference.startswith("SUP-")


async def test_support_stage_and_status_in_email(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: MakeApplication,
) -> None:
    """The email body carries CQ-031's stage label (spec.md's table) next
    to the raw internal status, for a NeedsAttention application."""
    application = await make_application()
    application.status = ApplicationStatus.NEEDS_ATTENTION
    await db_session.commit()
    client_row = await _sign_in(db_session, make_borrower_session, application)

    response = await client.post("/api/v1/portal/support", json=_VALID_BODY)
    assert response.status_code == 200

    emails = (
        (
            await db_session.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    inbox_email = next(e for e in emails if e.to_email != client_row.email)
    assert "Application received" in inbox_email.html
    assert "needs_attention" in inbox_email.html
