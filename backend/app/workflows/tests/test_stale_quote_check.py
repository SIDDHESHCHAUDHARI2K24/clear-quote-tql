"""CQ-030: `StaleQuoteCheckWorkflow` runs `mark_stale` through the real
worker registration, with `now` injected by the caller or resolved by
`resolve_clock_now` (which honours `CLOCK_NOW`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.worker import Worker

from app.core import clock
from app.core.config import get_settings
from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.quotes.stale.schemas import StaleResult
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE
from app.workflows.stale_quote_check import StaleQuoteCheckWorkflow


async def _seed_grace(db: AsyncSession) -> uuid.UUID:
    users = await seed_users(db)
    await seed_providers(db)
    persona = next(p for p in load_persona_fixtures() if p["key"] == "grace_kim")
    result = await seed_persona(db, persona, lo_id=users.lo_ids[0], s3_client=None)
    return result.application_id


async def _status(db: AsyncSession, application_id: uuid.UUID) -> ApplicationStatus:
    return (
        await db.execute(select(Application.status).where(Application.id == application_id))
    ).scalar_one()


async def test_workflow_marks_stale_with_injected_now(
    db_session: AsyncSession, temporal_client: Client, temporal_worker: Worker
) -> None:
    grace_id = await _seed_grace(db_session)

    result = await temporal_client.execute_workflow(
        StaleQuoteCheckWorkflow.run,
        datetime.now(UTC).isoformat(),
        id=f"stale-test-{uuid.uuid4()}",
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    assert isinstance(result, StaleResult)
    assert result.applications_marked_stale == 1
    assert result.application_ids == [str(grace_id)]
    assert await _status(db_session, grace_id) is ApplicationStatus.STALE


async def test_workflow_resolves_clock_now_when_not_injected(
    db_session: AsyncSession,
    temporal_client: Client,
    temporal_worker: Worker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no `now` argument (the schedule case), the workflow uses the
    worker's `core/clock.now()`. A `CLOCK_NOW` 10 days in the past puts
    Grace's send (25 days ago) at 15 days old: nothing changes."""
    grace_id = await _seed_grace(db_session)
    frozen = get_settings().model_copy(
        update={"clock_now": (datetime.now(UTC) - timedelta(days=10)).isoformat()}
    )
    monkeypatch.setattr(clock, "get_settings", lambda: frozen)

    result = await temporal_client.execute_workflow(
        StaleQuoteCheckWorkflow.run,
        id=f"stale-test-{uuid.uuid4()}",
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
    )

    assert result == StaleResult()
    assert await _status(db_session, grace_id) is ApplicationStatus.SENT
