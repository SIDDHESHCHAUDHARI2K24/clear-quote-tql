"""CQ-028a lock hardening, minor 4: a pending `pipeline.resume_requested`
must not stay sticky after a crash. Past 60 s it is treated as expired and
the (idempotent) signal is sent again."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.applications.sections.tests.conftest import FakeTemporal
from app.features.applications.timeline.models import ActivityEvent
from app.workflows.constants import application_workflow_id

MakeApp = Callable[..., Awaitable[Application]]

_PRIOR = {
    "street_address": "9 Old Rd",
    "city": "Fort Wayne",
    "state": "in",
    "zip": "46802",
    "housing_status": "rent",
    "residence_years": 1,
    "residence_months": 0,
}


def _freeze(monkeypatch: pytest.MonkeyPatch, at: datetime) -> None:
    frozen = get_settings().model_copy(update={"clock_now": at.isoformat()})
    monkeypatch.setattr(clock, "get_settings", lambda: frozen)


async def _resume_events(db: AsyncSession, application_id: uuid.UUID) -> int:
    rows = (
        await db.execute(
            select(ActivityEvent.id).where(
                ActivityEvent.application_id == application_id,
                ActivityEvent.type == "pipeline.resume_requested",
            )
        )
    ).all()
    return len(rows)


async def test_pending_resume_expires_after_60_seconds(
    client: AsyncClient,
    make_app: MakeApp,
    db_session: AsyncSession,
    fake_temporal: FakeTemporal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t0 = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    app = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    workflow_id = application_workflow_id(str(app.id))
    base = f"/api/v1/applications/{app.id}"

    _freeze(monkeypatch, t0)
    first = (await client.post(f"{base}/housing_history", json=_PRIOR)).json()
    assert first["resume"] == {"requested": True, "reason": "started"}

    # 30 s later the run has still not picked it up: not repeated.
    _freeze(monkeypatch, t0 + timedelta(seconds=30))
    second = (await client.put(f"{base}/fields/borrower_email", json={"value": "a@e.w"})).json()
    assert second["resume"] == {"requested": True, "reason": "already_requested"}
    assert fake_temporal.signals == []

    # 61 s later (e.g. the API crashed before signalling): signal again.
    _freeze(monkeypatch, t0 + timedelta(seconds=61))
    third = (await client.put(f"{base}/fields/borrower_email", json={"value": "b@e.w"})).json()
    assert third["resume"] == {"requested": True, "reason": "resumed"}
    assert fake_temporal.signals == [workflow_id]
    assert await _resume_events(db_session, app.id) == 2

    # The fresh request is pending again.
    _freeze(monkeypatch, t0 + timedelta(seconds=70))
    fourth = (await client.put(f"{base}/fields/borrower_email", json={"value": "c@e.w"})).json()
    assert fourth["resume"] == {"requested": True, "reason": "already_requested"}
    assert fake_temporal.signals == [workflow_id]


async def test_pending_resume_expires_on_the_db_clock_under_a_frozen_clock(
    client: AsyncClient,
    make_app: MakeApp,
    db_session: AsyncSession,
    fake_temporal: FakeTemporal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With `CLOCK_NOW` frozen the app-clock age stays 0; the DB-clock age
    (`created_at`) still expires the pending resume."""
    app = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    base = f"/api/v1/applications/{app.id}"
    _freeze(monkeypatch, datetime(2026, 10, 17, 9, 0, tzinfo=UTC))

    first = (await client.post(f"{base}/housing_history", json=_PRIOR)).json()
    assert first["resume"] == {"requested": True, "reason": "started"}
    second = (await client.put(f"{base}/fields/borrower_email", json={"value": "a@e.w"})).json()
    assert second["resume"] == {"requested": True, "reason": "already_requested"}

    # The request was committed 61 s ago on the DB clock (API crashed).
    await db_session.execute(
        update(ActivityEvent)
        .where(
            ActivityEvent.application_id == app.id,
            ActivityEvent.type == "pipeline.resume_requested",
        )
        .values(created_at=func.now() - timedelta(seconds=61))
    )
    await db_session.flush()

    third = (await client.put(f"{base}/fields/borrower_email", json={"value": "b@e.w"})).json()
    assert third["resume"] == {"requested": True, "reason": "resumed"}
    assert fake_temporal.signals == [application_workflow_id(str(app.id))]
