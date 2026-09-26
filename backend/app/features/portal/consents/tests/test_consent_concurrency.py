"""CQ-033 hardening nit: two accepts of one consent at the same time pull
exactly once.

Real concurrency needs committed rows and a session per request, so this
module reuses CQ-028a's committing `db_session`, per-request `client` and
`_cleanup` fixtures (see `sections/tests/test_concurrency.py`) and its
`make_app` factory, and removes the rows those fixtures do not.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import timedelta
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import now
from app.features.applications.models import Application
from app.features.applications.sections.tests.conftest import make_app, staff  # noqa: F401
from app.features.applications.sections.tests.test_concurrency import (  # noqa: F401
    _cleanup,
    client,
    db_session,
)
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import BorrowerAccount
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.clients.models import Client as ClientModel
from app.features.notifications.outbox.models import OutboxEmail
from app.features.portal.consents.consent_text import HARD_PULL_TEXT_V1, HARD_PULL_TEXT_VERSION
from app.integrations.common.models import IntegrationCall
from app.integrations.credit.models import CreditPullType, ProviderCreditReport
from conftest import BorrowerSession, StaffSession

from .test_consents_api import sent  # noqa: F401  (fixture)

MakeApp = Callable[..., Awaitable[Application]]


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_consent_rows(
    _cleanup: None,  # noqa: F811  (set up first, so this tears down first)
    test_engine: AsyncEngine,
    staff: StaffSession,  # noqa: F811
) -> AsyncIterator[None]:
    """Rows `_cleanup` does not remove and that would block its deletes."""
    yield
    async with test_engine.begin() as conn:
        app_ids = select(Application.id).where(Application.lo_id == staff.user.id)
        client_ids = select(ClientModel.id).where(ClientModel.assigned_lo_id == staff.user.id)
        await conn.execute(delete(OutboxEmail).where(OutboxEmail.application_id.in_(app_ids)))
        await conn.execute(delete(BorrowerAccount).where(BorrowerAccount.client_id.in_(client_ids)))


async def test_concurrent_double_accept_pulls_once(
    client: AsyncClient,  # noqa: F811
    db_session: AsyncSession,  # noqa: F811
    make_app: MakeApp,  # noqa: F811
    make_borrower_session: Callable[..., Awaitable[BorrowerSession]],
    sent: list[dict[str, str]],  # noqa: F811
    test_engine: AsyncEngine,
) -> None:
    app = await make_app()
    assert app.los_loan_guid is not None
    db_session.add(
        ProviderCreditReport(
            loan_number=app.los_loan_guid,
            pull_type=CreditPullType.HARD_PULL,
            experian_score=700,
            equifax_score=710,
            transunion_score=720,
            middle_score=710,
            tradelines=[],
        )
    )
    consent = Consent(
        application_id=app.id,
        type=ConsentType.HARD_PULL,
        status=ConsentStatus.PENDING,
        requested_at=now(),
        expires_at=now() + timedelta(days=14),
    )
    db_session.add(consent)
    client_row = await db_session.get(ClientModel, app.client_id)
    await make_borrower_session(client_row=client_row)
    await db_session.commit()
    url = f"/api/v1/portal/consents/{consent.id}/accept"
    body = {
        "typed_name": "Test Borrower",
        "text_version": HARD_PULL_TEXT_VERSION,
        "text_sha256": hashlib.sha256(HARD_PULL_TEXT_V1.encode()).hexdigest(),
    }

    first, second = await asyncio.wait_for(
        asyncio.gather(client.post(url, json=body), client.post(url, json=body)), timeout=30
    )

    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert first.json()["status"] == second.json()["status"] == "accepted"
    async with AsyncSession(bind=test_engine) as check:
        summaries: Sequence[Any] = (
            (await check.execute(select(IntegrationCall.request_summary))).scalars().all()
        )
        pulls = [
            summary
            for summary in summaries
            if isinstance(summary, dict)
            and summary.get("pull_type") == "hard_pull"
            and summary.get("loan_number") == app.los_loan_guid
        ]
        completed = (
            await check.execute(
                select(func.count())
                .select_from(ActivityEvent)
                .where(
                    ActivityEvent.application_id == app.id,
                    ActivityEvent.type == "credit.hard_pull_completed",
                )
            )
        ).scalar_one()
    assert len(pulls) == 1
    assert completed == 1
    assert [mail["subject"] for mail in sent].count("Credit check authorized — FICO 710") == 1
