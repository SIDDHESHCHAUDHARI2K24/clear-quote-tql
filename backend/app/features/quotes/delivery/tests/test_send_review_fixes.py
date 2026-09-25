"""CQ-020 PR #30 review-fix round: double send, dead sends, and the minor
findings (post-dev.md "Review findings", plan.md Decisions 22-23).

Workflow-test rules (docs/backlog/p34-test-flake-fix.md): every workflow a
test starts is awaited or terminated before the test returns, and the test's
own `db_session` is only queried while no activity can be running.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle
from temporalio.service import RPCError, RPCStatusCode

from app.core.enums import ApplicationStatus
from app.features.applications.models import Application
from app.features.notifications.email import service as email_service
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail
from app.features.quotes.builder.tests.test_router import _seed
from app.features.quotes.delivery import service as delivery_service
from app.features.quotes.delivery import steps
from app.features.quotes.delivery.tests.test_send import (
    MakeStaff,
    _ready_package,
    _send,
    _versions,
)
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from app.features.quotes.send.service import get_or_create_package
from app.integrations.crm.models import CrmEvent
from app.workflows import db as workflow_db
from app.workflows import send_activities
from app.workflows.client import get_temporal_client
from app.workflows.constants import send_workflow_id
from app.workflows.send_quote_package import SendQuotePackageWorkflow

from .conftest import SentMail

STOPPED = "The send stopped before finishing. Try again."
GENERIC = "The send failed. Try again."


async def _status(client: AsyncClient, package_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/packages/{package_id}/send-status")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _terminate(handle: WorkflowHandle[Any, Any]) -> None:
    """Rule 1: never leave a started workflow running past the test."""
    try:
        await handle.terminate("test cleanup")
    except Exception:  # noqa: BLE001 -- already finished is fine
        pass


def _put_body(package: dict[str, Any]) -> dict[str, Any]:
    return {"quote_ids": package["quote_ids"], "recommended_quote_id": package["quote_ids"][0]}


# --- MAJOR 1: a double click must never send twice -------------------------


class _SlowStartClient:
    """The real test-env client, but `start_workflow` takes 300 ms to reach
    the server -- the window in which a second POST used to see `queued`
    with a workflow Temporal didn't know yet, and start a second send."""

    def __init__(self, inner: Client) -> None:
        self.inner = inner
        self.started: list[str] = []

    def get_workflow_handle(self, *args: Any, **kwargs: Any) -> Any:
        return self.inner.get_workflow_handle(*args, **kwargs)

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.3)
        handle = await self.inner.start_workflow(*args, **kwargs)
        self.started.append(kwargs["id"])
        return handle


async def _table_counts(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as conn:
        tables: list[str] = list(
            (
                await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            ).scalars()
        )
        counts: dict[str, int] = {}
        for table in tables:
            counts[table] = (
                await conn.execute(text(f'SELECT count(*) FROM "{table}"'))  # noqa: S608
            ).scalar_one()
        return counts


@asynccontextmanager
async def _committed_data(engine: AsyncEngine) -> AsyncIterator[None]:
    """This test needs two requests on two real connections, so its data is
    really committed (the usual `db_session` rollback can't be seen from a
    second connection). Afterwards every table that was empty before is
    emptied again, and nothing else may have changed. Not `TRUNCATE ...
    CASCADE`: that would also empty `settings` (it references `users`)."""
    before = await _table_counts(engine)
    try:
        yield
    finally:
        after = await _table_counts(engine)
        dirty = [t for t, n in after.items() if before.get(t, 0) == 0 and n > 0]
        if dirty:
            async with engine.begin() as conn:
                # Skip FK triggers so the rows can go in any order.
                await conn.execute(text("SET LOCAL session_replication_role = replica"))
                for table in dirty:
                    await conn.execute(text(f'DELETE FROM "{table}"'))  # noqa: S608
        changed = {
            t: (before[t], n) for t, n in after.items() if before.get(t, 0) > 0 and before[t] != n
        }
        assert not changed, f"committed test data leaked into non-empty tables: {changed}"


async def test_concurrent_posts_send_once(
    test_engine: AsyncEngine,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two POSTs that genuinely overlap (two connections, the first one's
    workflow start still in flight when the second takes the package lock)
    start one workflow and send one email: one version."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(workflow_db, "session_factory", factory)
    temporal = _SlowStartClient(temporal_client_override)
    started: list[str] = []

    async with _committed_data(test_engine):
        async with factory() as db:
            ids = await _seed(db, "marcus_hale")
            await db.commit()
            application = await db.get(Application, ids["marcus_hale"])
            assert application is not None
            package_id = (await get_or_create_package(db, application)).id
            await db.commit()

        async def post() -> str:
            async with factory() as db:
                package = await db.get(QuotePackage, package_id)
                assert package is not None
                started_send = await delivery_service.start_send(
                    db, package, cast(Client, temporal)
                )
                return started_send.workflow_id

        try:
            first, second = await asyncio.gather(post(), post())
            started = list(temporal.started)
            assert first == second
            assert started == [first]
            async with run_send_worker():
                for workflow_id in started:
                    await temporal_client_override.get_workflow_handle(workflow_id).result()
            async with factory() as db:
                versions = (
                    (
                        await db.execute(
                            select(QuotePackageVersion).where(
                                QuotePackageVersion.package_id == package_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            assert len(versions) == 1
            assert len(smtp_outbox) == 1
        finally:
            for workflow_id in temporal.started:
                await _terminate(temporal_client_override.get_workflow_handle(workflow_id))


async def test_superseded_run_is_a_noop(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    send_queue: str,
    smtp_outbox: list[SentMail],
) -> None:
    """A run that is no longer the package's current send freezes nothing,
    sends nothing, and doesn't mark the package failed."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    newer = send_workflow_id(package["id"], "newer")
    await db_session.execute(
        update(QuotePackage)
        .where(QuotePackage.id == uuid.UUID(package["id"]))
        .values(send_workflow_id=newer, send_status="queued")
    )
    await db_session.commit()

    async with run_send_worker():
        result = await temporal_client_override.execute_workflow(
            SendQuotePackageWorkflow.run,
            package["id"],
            id=send_workflow_id(package["id"], "stale"),
            task_queue=send_queue,
        )
    assert result == ""
    row = await db_session.get(QuotePackage, uuid.UUID(package["id"]), populate_existing=True)
    assert row is not None
    assert (row.send_workflow_id, row.send_status, row.send_error) == (newer, "queued", None)
    assert await _versions(db_session, package["id"]) == []
    assert smtp_outbox == []


# --- MAJOR 2: a dead send must not lock the package forever ----------------


async def test_send_workflow_has_an_execution_timeout(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    send_queue: str,
) -> None:
    """With no worker, the workflow can't wait forever: Temporal times it
    out, and the next read reports `failed`."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    assert response.status_code == 202
    handle = temporal_client_override.get_workflow_handle(response.json()["workflow_id"])
    try:
        description = await handle.describe()
        timeout = description.raw_description.execution_config.workflow_execution_timeout
        assert timeout.ToSeconds() == 600
    finally:
        await _terminate(handle)


async def test_status_reports_a_terminated_send_as_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    send_queue: str,
) -> None:
    _, package = await _ready_package(client, db_session, make_staff_session)
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    handle = temporal_client_override.get_workflow_handle(response.json()["workflow_id"])
    try:
        assert (await _status(client, package["id"]))["status"] == "queued"
    finally:
        await _terminate(handle)
    status = await _status(client, package["id"])
    assert (status["status"], status["error"]) == ("failed", STOPPED)


async def test_put_after_a_terminated_send_saves(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    send_queue: str,
) -> None:
    """While the workflow runs the PUT is a 409; once it's gone, the PUT
    marks the dead send failed and saves."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    url = f"/api/v1/applications/{application_id}/package"
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    handle = temporal_client_override.get_workflow_handle(response.json()["workflow_id"])
    try:
        blocked = await client.put(url, json=_put_body(package))
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "SEND_IN_PROGRESS"
    finally:
        await _terminate(handle)
    saved = await client.put(url, json=_put_body(package))
    assert saved.status_code == 200, saved.text
    status = await _status(client, package["id"])
    assert (status["status"], status["error"]) == ("failed", STOPPED)


async def test_cancelled_send_is_marked_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """The workflow catches cancellation and runs `mark_send_failed`."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    handle = temporal_client_override.get_workflow_handle(response.json()["workflow_id"])
    await handle.cancel()
    async with run_send_worker():
        with pytest.raises(WorkflowFailureError):
            await handle.result()
    row = await db_session.get(QuotePackage, uuid.UUID(package["id"]), populate_existing=True)
    assert row is not None
    assert (row.send_status, row.send_error) == ("failed", STOPPED)
    assert smtp_outbox == []


# --- RE-REVIEW 1: start_workflow raising after Temporal accepted the run ----


class _AcceptThenFailClient:
    """The real test-env client, but `start_workflow` raises *after* the run
    has actually started against Temporal -- the client-side failure (e.g.
    an RPC deadline) that PR #30 re-review minor 1 is about: Temporal
    already has the run, but the caller never gets the happy return."""

    def __init__(self, inner: Client) -> None:
        self.inner = inner
        self.started: list[str] = []

    def get_workflow_handle(self, *args: Any, **kwargs: Any) -> Any:
        return self.inner.get_workflow_handle(*args, **kwargs)

    async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
        await self.inner.start_workflow(*args, **kwargs)
        self.started.append(kwargs["id"])
        raise RPCError("deadline exceeded", RPCStatusCode.DEADLINE_EXCEEDED, b"")


async def test_start_send_orphan_is_superseded_not_double_sent(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """PR #30 re-review minor 1: `start_send` must not point the package at
    the orphan run's id -- only ever record the failure against whatever
    `send_workflow_id` it had before -- or Freeze's `SendSupersededError`
    guard (Decision 22) can't tell the orphan apart from a real send, and a
    retry races it into double-emailing."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    package_id = uuid.UUID(package["id"])
    row = await db_session.get(QuotePackage, package_id)
    assert row is not None
    assert row.send_workflow_id is None
    temporal = _AcceptThenFailClient(temporal_client_override)

    with pytest.raises(delivery_service.SendUnavailableError):
        await delivery_service.start_send(db_session, row, cast(Client, temporal))
    await db_session.commit()

    [orphan_id] = temporal.started
    row = await db_session.get(QuotePackage, package_id, populate_existing=True)
    assert row is not None
    assert row.send_workflow_id is None  # unchanged: never the orphan's id
    assert (row.send_status, row.send_error) == ("failed", "The send could not be started.")

    try:
        async with run_send_worker():
            result = await temporal_client_override.get_workflow_handle(orphan_id).result()
        assert result == ""  # Freeze found itself superseded and stopped: no version, no email
    finally:
        await _terminate(temporal_client_override.get_workflow_handle(orphan_id))
    assert await _versions(db_session, package["id"]) == []
    assert smtp_outbox == []

    # A retry starts a fresh, tracked send and completes normally -- once.
    async with run_send_worker():
        retried = await _send(client, temporal_client_override, package["id"])
    assert retried["workflow_id"] != orphan_id
    assert len(await _versions(db_session, package["id"])) == 1
    assert len(smtp_outbox) == 1


# --- RE-REVIEW 2: reconcile must survive an unreachable Temporal -----------


async def test_reconcile_survives_an_unreachable_temporal_provider(
    app: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
) -> None:
    """PR #30 re-review minor 2: `await temporal()` -- the lazy provider
    itself -- used to run outside `_send_is_alive`'s `try`. On a fresh
    process with Temporal unreachable, that raised straight out of
    `reconcile_send` and 500'd `GET /send-status` and `PUT /package` instead
    of treating an unreachable Temporal as "still in flight"."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    workflow_id = send_workflow_id(package["id"], "unreachable")
    await db_session.execute(
        update(QuotePackage)
        .where(QuotePackage.id == uuid.UUID(package["id"]))
        .values(send_workflow_id=workflow_id, send_status="rendering")
    )
    await db_session.commit()

    async def _unreachable() -> Client:
        raise ConnectionError("temporal down")

    app.dependency_overrides[get_temporal_client] = _unreachable
    status_response = await client.get(f"/api/v1/packages/{package['id']}/send-status")
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["status"] == "rendering"

    put_response = await client.put(
        f"/api/v1/applications/{application_id}/package", json=_put_body(package)
    )
    assert put_response.status_code == 409, put_response.text
    assert put_response.json()["error"]["code"] == "SEND_IN_PROGRESS"


# --- RE-REVIEW 4: rpc_timeout on calls made while the row lock is held -----


async def test_start_send_and_workflow_running_pass_an_rpc_timeout(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
) -> None:
    """PR #30 re-review minor 4: `start_workflow` and the describe call
    `reconcile`/the double-click check make both run while the package row
    lock is held, so neither should be able to hang on Temporal."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    row = await db_session.get(QuotePackage, uuid.UUID(package["id"]))
    assert row is not None
    captured_start: dict[str, Any] = {}
    captured_describe: dict[str, Any] = {}

    class _Spy:
        def get_workflow_handle(self, *args: Any, **kwargs: Any) -> Any:
            handle = temporal_client_override.get_workflow_handle(*args, **kwargs)

            class _HandleSpy:
                async def describe(self, **kw: Any) -> Any:
                    captured_describe.update(kw)
                    return await handle.describe(**kw)

            return _HandleSpy()

        async def start_workflow(self, *args: Any, **kwargs: Any) -> Any:
            captured_start.update(kwargs)
            return await temporal_client_override.start_workflow(*args, **kwargs)

    try:
        started = await delivery_service.start_send(db_session, row, cast(Client, _Spy()))
        await db_session.commit()
        assert captured_start.get("rpc_timeout") == delivery_service.TEMPORAL_RPC_TIMEOUT

        await delivery_service._workflow_running(cast(Client, _Spy()), started.workflow_id)
        assert captured_describe.get("rpc_timeout") == delivery_service.TEMPORAL_RPC_TIMEOUT
    finally:
        await _terminate(temporal_client_override.get_workflow_handle(started.workflow_id))


# --- MINOR a: the PUT/POST race ----------------------------------------------


async def test_put_rereads_send_status_under_lock(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    send_queue: str,
) -> None:
    """The PUT locks the package and re-reads it: a send the session's
    cached copy doesn't know about yet still refuses the edit."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    package_id = uuid.UUID(package["id"])
    held = await db_session.get(QuotePackage, package_id)  # a cached, idle copy
    assert held is not None and held.send_status is None
    workflow_id = send_workflow_id(package["id"], "elsewhere")
    handle = await temporal_client_override.start_workflow(
        SendQuotePackageWorkflow.run, package["id"], id=workflow_id, task_queue=send_queue
    )
    try:
        await db_session.execute(
            update(QuotePackage)
            .where(QuotePackage.id == package_id)
            .values(send_workflow_id=workflow_id, send_status="rendering")
            .execution_options(synchronize_session=False)
        )
        await db_session.commit()
        assert held.send_status is None  # still stale
        response = await client.put(
            f"/api/v1/applications/{application_id}/package", json=_put_body(package)
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "SEND_IN_PROGRESS"
    finally:
        await _terminate(handle)


def test_letter_takes_note_and_recommendation_from_the_snapshot() -> None:
    live = QuotePackage(
        id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        lo_note="edited after freeze",
        recommendation_text="edited after freeze",
    )
    quote_id = str(uuid.uuid4())
    snapshot = {
        "options": [{"quote_id": quote_id, "recommended": True}],
        "recommendation": {"text": "frozen text", "lo_note": "frozen note"},
    }
    frozen = steps._frozen_package(live, snapshot)
    assert frozen.lo_note == "frozen note"
    assert frozen.recommendation_text == "frozen text"
    assert frozen.quote_ids == [uuid.UUID(quote_id)]


# --- MINOR b: no raw exception text in send_error ---------------------------


async def test_unexpected_failure_shows_a_generic_error(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    _, package = await _ready_package(client, db_session, make_staff_session)

    @activity.defn(name="render_letter_pdf")
    async def _broken(version_id: str, workflow_id: str) -> str:
        raise RuntimeError("connect to minio:9000 failed: /secret/internal/path")

    activities: list[Callable[..., Awaitable[Any]]] = [
        send_activities.freeze_package,
        _broken,
        send_activities.email_borrower,
        send_activities.record_send,
        send_activities.mark_send_failed,
    ]
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    async with run_send_worker(activities):
        with pytest.raises(WorkflowFailureError):
            await temporal_client_override.get_workflow_handle(
                response.json()["workflow_id"]
            ).result()
    status = await _status(client, package["id"])
    assert (status["status"], status["error"]) == ("failed", GENERIC)


# --- MINOR c: no borrower address in the logs --------------------------------


async def test_delivery_failure_logs_the_outbox_id_not_the_address(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def _down(**_: Any) -> None:
        raise ConnectionError("smtp down")

    monkeypatch.setattr(email_service, "smtp_send", _down)
    # `alembic upgrade head` (test_engine) runs `fileConfig`, which disables
    # every logger that already existed.
    monkeypatch.setattr(email_service.logger, "disabled", False)
    outbox = OutboxEmail(
        to_email="private.person@example.test",
        subject="s",
        html="<p>h</p>",
        status=EmailStatus.QUEUED,
    )
    db_session.add(outbox)
    await db_session.flush()
    with caplog.at_level(logging.ERROR), pytest.raises(ConnectionError):
        await email_service.deliver_outbox_email(db_session, outbox)
    assert "private.person@example.test" not in caplog.text
    assert str(outbox.id) in caplog.text


# --- MINOR d / e / f: freeze and record --------------------------------------


async def test_send_keeps_the_draft_expiry_and_crm_carries_no_token(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    temporal_client_override: Client,
    run_send_worker: Any,
    smtp_outbox: list[SentMail],
) -> None:
    """d: the package's own 7-day `expires_at` is untouched (D2: the version
    holds the 21-day expiry). f: the CRM event names the version, never the
    tokened report URL."""
    _, package = await _ready_package(client, db_session, make_staff_session)
    row = await db_session.get(QuotePackage, uuid.UUID(package["id"]))
    assert row is not None
    draft_expiry = row.expires_at
    response = await client.post(f"/api/v1/packages/{package['id']}/send")
    async with run_send_worker():
        await temporal_client_override.get_workflow_handle(response.json()["workflow_id"]).result()

    row = await db_session.get(QuotePackage, uuid.UUID(package["id"]), populate_existing=True)
    assert row is not None and row.expires_at == draft_expiry
    [version] = await _versions(db_session, package["id"])
    [crm] = (
        (
            await db_session.execute(
                select(CrmEvent).where(
                    CrmEvent.event_type == "quote.sent",
                    CrmEvent.payload["package_id"].astext == package["id"],
                )
            )
        )
        .scalars()
        .all()
    )
    assert isinstance(crm.payload, dict)
    assert crm.payload["version_id"] == str(version.id)
    assert "report_url" not in crm.payload
    assert version.report_token not in str(crm.payload)


async def test_freeze_refuses_a_closed_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
) -> None:
    """e: Freeze re-checks the same blockers as POST, `application_closed`
    included (the application was withdrawn after the POST)."""
    application_id, package = await _ready_package(client, db_session, make_staff_session)
    workflow_id = send_workflow_id(package["id"], "closed")
    await db_session.execute(
        update(QuotePackage)
        .where(QuotePackage.id == uuid.UUID(package["id"]))
        .values(send_workflow_id=workflow_id, send_status="queued")
    )
    application = await db_session.get(Application, application_id)
    assert application is not None
    application.status = ApplicationStatus.WITHDRAWN
    await db_session.commit()
    with pytest.raises(steps.PackageNotReadyError, match="The application is withdrawn"):
        await steps.freeze(db_session, uuid.UUID(package["id"]), workflow_id)
    assert await _versions(db_session, package["id"]) == []
