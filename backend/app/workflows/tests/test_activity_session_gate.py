"""Regression guard for the P3/P4 workflow-test flake
(docs/backlog/p34-test-flake-fix.md).

Workflow tests bind every activity session to the test's own `db_session`
connection. Before the fix, `wait_for_status` could observe a status the
activity had only *flushed* (same connection, same transaction) while
that activity was still mid-way through its remaining writes, so the
test asserted early and tore down `db_session` under a running activity
-- asyncpg's "another operation is in progress", then a poisoned
connection for every later test. These tests pin the gate that stops it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.workflows import db as workflow_db
from app.workflows.tests.conftest import ActivitySessionGate


async def test_wait_for_status_returns_only_after_the_writing_activity_closes(
    db_session: AsyncSession,
    make_persona_application: Callable[..., Awaitable[Application]],
    wait_for_status: Callable[..., Awaitable[ApplicationStatus]],
) -> None:
    application = await make_persona_application()
    activity_closed = asyncio.Event()
    status_flushed = asyncio.Event()

    async def _fake_activity() -> None:
        # Mirrors `_fail_pricing_stage`: flush the status first, then keep
        # writing on the same session before closing it.
        async with workflow_db.session_factory() as db:
            row = await db.get(Application, application.id)
            assert row is not None
            row.status = ApplicationStatus.NEEDS_ATTENTION
            await db.flush()
            status_flushed.set()
            await asyncio.sleep(0.2)
            await db.execute(text("SELECT 1"))
            await db.commit()
        activity_closed.set()

    task = asyncio.create_task(_fake_activity())
    await status_flushed.wait()

    await wait_for_status(db_session, application.id, {ApplicationStatus.NEEDS_ATTENTION})

    assert activity_closed.is_set()
    await task


async def test_test_turn_blocks_new_activity_sessions(
    activity_session_gate: ActivitySessionGate,
) -> None:
    entered = asyncio.Event()

    async def _fake_activity() -> None:
        async with workflow_db.session_factory():
            entered.set()

    async with activity_session_gate.test_turn():
        task = asyncio.create_task(_fake_activity())
        await asyncio.sleep(0.05)
        assert not entered.is_set()
    await asyncio.wait_for(task, timeout=1.0)
    assert entered.is_set()
    assert activity_session_gate.in_flight == 0
