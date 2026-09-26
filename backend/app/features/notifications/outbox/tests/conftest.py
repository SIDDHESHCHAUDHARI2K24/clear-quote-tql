"""Local fixtures for `notifications/outbox/tests/` (established per
subpackage `make_application` pattern, see `applications/summary/tests/
conftest.py`)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail


@pytest_asyncio.fixture
async def make_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(lo: User | None = None, **overrides: object) -> Application:
        if lo is None:
            lo = User(
                email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
                password_hash="not-a-real-hash",
                role=UserRole.LO,
                full_name="Test LO",
            )
            db_session.add(lo)
            await db_session.flush()

        client = Client(
            full_name="Test Client",
            email=f"client-{uuid.uuid4()}@clearquote-demo.test",
            assigned_lo_id=lo.id,
        )
        db_session.add(client)
        await db_session.flush()

        defaults: dict[str, object] = {"occupancy": Occupancy.PRIMARY, "program": "Conventional"}
        defaults.update(overrides)
        application = Application(client_id=client.id, lo_id=lo.id, **defaults)
        db_session.add(application)
        await db_session.flush()
        return application

    return _make


@pytest_asyncio.fixture
async def make_outbox_email(db_session: AsyncSession) -> Callable[..., Awaitable[OutboxEmail]]:
    async def _make(
        *,
        application: Application | None = None,
        to_email: str = "borrower@example.com",
        subject: str = "Your Clear Quote sign-in code",
        html: str = "<p>hi</p>",
        status: EmailStatus = EmailStatus.SENT,
        attachment_keys: list[str] | None = None,
    ) -> OutboxEmail:
        email = OutboxEmail(
            to_email=to_email,
            subject=subject,
            html=html,
            attachment_keys=attachment_keys or [],
            status=status,
            application_id=application.id if application is not None else None,
        )
        db_session.add(email)
        await db_session.flush()
        return email

    return _make
