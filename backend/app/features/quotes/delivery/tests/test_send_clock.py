"""U3 (merge plan M5): one clock across CQ-018 re-price, CQ-020 send and
CQ-030's stale job.

CQ-030 AC3 through the real CQ-020 path (`POST /packages/{id}/send` + the
`SendQuotePackage` workflow and activities in the Temporal test env) with
`CLOCK_NOW` frozen far from the real clock: the re-price stamps
`priced_at`, the Freeze step stamps `sent_at`/`expires_at`, and
`mark_stale` at +20 days changes nothing while +22 days makes Marcus Stale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core import clock
from app.core.config import get_settings
from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.quotes.stale.schemas import StaleResult
from app.features.quotes.stale.service import mark_stale

from .conftest import SentMail
from .test_send import MakeStaff, _ready_package, _send, _versions


def _freeze(monkeypatch: pytest.MonkeyPatch, at: datetime) -> None:
    frozen = get_settings().model_copy(update={"clock_now": at.isoformat()})
    monkeypatch.setattr(clock, "get_settings", lambda: frozen)


async def _status(db: AsyncSession, application_id: Any) -> ApplicationStatus:
    application = await db.get(Application, application_id, populate_existing=True)
    assert application is not None
    return application.status


async def test_send_under_clock_now_then_mark_stale_at_20_and_22_days(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    # 100 days ahead of the real clock: any real-clock stamp would be >21
    # days older than this "now" and show up as stale below.
    t0 = datetime.now(UTC).replace(microsecond=0) + timedelta(days=100)
    _freeze(monkeypatch, t0)

    repriced = await client.post(f"/api/v1/applications/{application_id}/reprice")
    assert repriced.status_code == 200, repriced.text
    assert datetime.fromisoformat(repriced.json()["priced_at"]) == t0
    readiness = (await client.get(f"/api/v1/packages/{package['id']}/readiness")).json()
    assert readiness == {"ready": True, "blockers": []}

    async with run_send_worker():
        await _send(client, temporal_client_override, package["id"])

    [version] = await _versions(db_session, package["id"])
    assert version.sent_at == t0
    assert version.expires_at == t0 + timedelta(days=21)
    assert await _status(db_session, application_id) is ApplicationStatus.SENT

    _freeze(monkeypatch, t0 + timedelta(days=20))
    assert await mark_stale(db_session, clock.now()) == StaleResult()
    assert await _status(db_session, application_id) is ApplicationStatus.SENT

    _freeze(monkeypatch, t0 + timedelta(days=22))
    result = await mark_stale(db_session, clock.now())
    assert result.applications_marked_stale == 1
    assert result.versions_expired == 1
    assert await _status(db_session, application_id) is ApplicationStatus.STALE
