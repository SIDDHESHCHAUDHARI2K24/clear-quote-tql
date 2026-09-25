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

import pytest
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


async def test_closed_gate_rejects_new_activity_sessions(
    activity_session_gate: ActivitySessionGate,
) -> None:
    """Reviewer finding #1: `wait_idle()` only guards activities already
    running at teardown. `close()` covers the gap after it -- a workflow
    from this test that starts a *new* activity once `db_session` is about
    to roll back must fail loudly instead of touching the connection."""
    await activity_session_gate.close()

    with pytest.raises(RuntimeError, match="activity started after test teardown"):
        await activity_session_gate.enter_activity()


async def test_test_turn_times_out_with_assertion_naming_in_flight_count(
    activity_session_gate: ActivitySessionGate,
) -> None:
    """Reviewer finding #2: an activity session that never closes must not
    hang `test_turn()` (and therefore `wait_for_status`) forever."""
    await activity_session_gate.enter_activity()
    try:
        with pytest.raises(AssertionError, match=r"1 in-flight activity session"):
            async with activity_session_gate.test_turn(timeout=0.05):
                pass
    finally:
        await activity_session_gate.exit_activity()


async def test_exit_activity_decrement_survives_notify_cancellation(
    activity_session_gate: ActivitySessionGate,
) -> None:
    """Reviewer finding #3: the in-flight count must drop even if the
    caller of `exit_activity()` (`_GatedActivitySession.__aexit__`) is
    cancelled while the wake-up notification is still in flight -- the
    decrement itself must never depend on completing that await."""
    await activity_session_gate.enter_activity()
    assert activity_session_gate.in_flight == 1

    task = asyncio.create_task(activity_session_gate.exit_activity())
    # Let the task run its first step -- the synchronous decrement plus
    # entering the shielded notify -- then cancel it while it's suspended
    # waiting on that shield.
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert activity_session_gate.in_flight == 0
