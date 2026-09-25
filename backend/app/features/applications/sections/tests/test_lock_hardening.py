"""CQ-028a lock hardening (round-2 review minors 1, 2, 3 and 5b).

These tests need real concurrency, so they reuse `test_concurrency`'s
committing `db_session`, per-request `client` and `_cleanup` fixtures:
every check runs against a second, independent connection.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from temporalio.service import RPCError, RPCStatusCode

from app.core.enums import ApplicationStatus, FlagSeverity
from app.features.applications.locking import lock_application
from app.features.applications.models import Application
from app.features.applications.sections.reverify import get_temporal_provider
from app.features.applications.sections.tests.test_concurrency import (  # noqa: F401
    _cleanup,
    client,
    db_session,
)
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import Flag
from app.integrations.los.mock import MockLosClient
from app.workflows import db as workflow_db
from app.workflows.activities import verify_application

MakeApp = Callable[..., Awaitable[Application]]


async def _lock_is_free(engine: AsyncEngine, application_id: uuid.UUID) -> bool:
    """From a fresh connection: can another holder take the application
    lock right now? (`lock_timeout` turns a wait into an error.)"""
    async with AsyncSession(bind=engine) as other:
        await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
        try:
            await lock_application(other, application_id)
        except DBAPIError:
            return False
        finally:
            await other.rollback()
    return True


# --- minor 3: FOR NO KEY UPDATE ---------------------------------------------


async def test_lock_does_not_block_inserts_referencing_the_application(
    make_app: MakeApp, test_engine: AsyncEngine
) -> None:
    """An FK insert takes FOR KEY SHARE on `applications`; FOR UPDATE blocked
    it (and deadlocked with a holder that then waited on the inserter)."""
    app = await make_app()
    async with AsyncSession(bind=test_engine) as holder, AsyncSession(bind=test_engine) as other:
        await lock_application(holder, app.id)

        await other.execute(text("SET LOCAL lock_timeout = '1s'"))
        other.add(
            ActivityEvent(
                application_id=app.id,
                actor="system",
                type="test.fk_insert",
                payload={},
                at=func.now(),
            )
        )
        await other.commit()  # raises LockNotAvailable if blocked

        # The holder can still update the row it locked.
        await holder.execute(
            text("UPDATE applications SET updated_at = now() WHERE id = :id"), {"id": app.id}
        )
        await holder.commit()


async def test_lock_holders_still_serialise(make_app: MakeApp, test_engine: AsyncEngine) -> None:
    """Two `lock_application` holders, and a holder against CQ-030's
    `mark_stale`-style `FOR UPDATE`, still exclude each other."""
    app = await make_app()
    async with AsyncSession(bind=test_engine) as holder:
        await lock_application(holder, app.id)
        assert not await _lock_is_free(test_engine, app.id)

        async with AsyncSession(bind=test_engine) as stale_job:
            await stale_job.execute(text("SET LOCAL lock_timeout = '200ms'"))
            with pytest.raises(DBAPIError):
                await stale_job.execute(
                    select(Application.id).where(Application.id == app.id).with_for_update()
                )
            await stale_job.rollback()
        await holder.rollback()

    assert await _lock_is_free(test_engine, app.id)

    # And a waiting holder proceeds once the first one commits.
    order: list[str] = []

    async def _hold(name: str, delay: float) -> None:
        async with AsyncSession(bind=test_engine) as session:
            await asyncio.sleep(delay)
            await lock_application(session, app.id)
            order.append(f"{name}:locked")
            await asyncio.sleep(0.3)
            order.append(f"{name}:released")
            await session.commit()

    await asyncio.wait_for(asyncio.gather(_hold("a", 0), _hold("b", 0.1)), timeout=10)
    assert order == ["a:locked", "a:released", "b:locked", "b:released"]


# --- minor 2: LOS fetch outside the lock ------------------------------------


async def test_import_liabilities_fetches_the_loan_file_before_locking(
    client: AsyncClient,  # noqa: F811
    make_app: MakeApp,
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = await make_app()
    original = MockLosClient.get_loan_file
    free_during_fetch: list[bool] = []

    async def _spy(self: MockLosClient, loan_number: str) -> Any:
        free_during_fetch.append(await _lock_is_free(test_engine, app.id))
        return await original(self, loan_number)

    monkeypatch.setattr(MockLosClient, "get_loan_file", _spy)

    response = await client.post(f"/api/v1/applications/{app.id}/credit/import-liabilities")

    assert response.status_code == 200, response.text
    assert free_during_fetch == [True]


# --- minor 1: Temporal describe outside the lock ----------------------------


@dataclass
class _SlowHandle:
    temporal: _SlowTemporal

    async def describe(self, **kwargs: Any) -> Any:
        self.temporal.describe_kwargs.append(kwargs)
        await asyncio.sleep(0.2)  # a slow Temporal frontend
        self.temporal.free_during_describe.append(
            await _lock_is_free(self.temporal.engine, self.temporal.application_id)
        )
        raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")

    async def signal(self, _signal: Any) -> None:  # pragma: no cover - not reached
        raise AssertionError("no run exists")


@dataclass
class _SlowTemporal:
    engine: AsyncEngine
    application_id: uuid.UUID
    describe_kwargs: list[dict[str, Any]] = field(default_factory=list)
    free_during_describe: list[bool] = field(default_factory=list)
    starts: list[str] = field(default_factory=list)

    def get_workflow_handle(self, _workflow_id: str) -> _SlowHandle:
        return _SlowHandle(self)

    async def start_workflow(self, *_args: Any, id: str, **_kwargs: Any) -> None:  # noqa: A002
        self.starts.append(id)


@pytest_asyncio.fixture
async def slow_temporal_for(app: FastAPI) -> AsyncIterator[Callable[..., _SlowTemporal]]:
    def _install(engine: AsyncEngine, application_id: uuid.UUID) -> _SlowTemporal:
        fake = _SlowTemporal(engine, application_id)

        async def _client() -> Any:
            return fake

        async def _provider() -> Any:
            return _client

        app.dependency_overrides[get_temporal_provider] = _provider
        return fake

    yield _install


async def test_describe_runs_outside_the_lock_with_a_short_timeout(
    client: AsyncClient,  # noqa: F811
    make_app: MakeApp,
    test_engine: AsyncEngine,
    slow_temporal_for: Callable[..., _SlowTemporal],
) -> None:
    app = await make_app(housing=[(1, 2)], status=ApplicationStatus.NEEDS_ATTENTION)
    fake = slow_temporal_for(test_engine, app.id)

    response = await client.post(
        f"/api/v1/applications/{app.id}/housing_history",
        json={
            "street_address": "9 Old Rd",
            "city": "Fort Wayne",
            "state": "in",
            "zip": "46802",
            "housing_status": "rent",
            "residence_years": 1,
            "residence_months": 0,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["resume"] == {"requested": True, "reason": "started"}
    assert fake.free_during_describe == [True]
    timeout = fake.describe_kwargs[0]["rpc_timeout"]
    assert timeout.total_seconds() <= 5


# --- minor 5b: pipeline verify racing an LO edit ----------------------------


async def test_pipeline_verify_and_edit_race_ends_consistent(
    client: AsyncClient,  # noqa: F811
    make_app: MakeApp,
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`verify_application` (flags + status in one locked transaction) and a
    PUT that fixes the blocking flag, run concurrently: no deadlock, and the
    final state is one of the two serial outcomes."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(workflow_db, "session_factory", factory)

    for _ in range(4):
        app = await make_app(ssn="12")  # invalid: a blocking ssn_format flag
        await asyncio.wait_for(
            asyncio.gather(
                verify_application(str(app.id)),
                client.put(
                    f"/api/v1/applications/{app.id}/fields/borrower_ssn",
                    json={"value": "123456789"},
                ),
            ),
            timeout=20,
        )

        async with factory() as check:
            blocking = (
                await check.execute(
                    select(func.count(Flag.id)).where(
                        Flag.application_id == app.id,
                        Flag.resolved_at.is_(None),
                        Flag.severity == FlagSeverity.BLOCKING,
                    )
                )
            ).scalar_one()
            status = (
                await check.execute(select(Application.status).where(Application.id == app.id))
            ).scalar_one()
            types = list(
                (
                    await check.execute(
                        select(ActivityEvent.type).where(ActivityEvent.application_id == app.id)
                    )
                )
                .scalars()
                .all()
            )

        assert blocking == 0
        if status is ApplicationStatus.NEEDS_ATTENTION:
            # verify ran first; the edit then cleared the flag and resumed.
            assert "pipeline.resume_requested" in types
        else:
            # the edit ran first; verify then saw the fixed SSN.
            assert status is ApplicationStatus.READY_TO_PRICE
