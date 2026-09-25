"""Fixtures for the CQ-020 send tests.

- `bind_activities_to_test_session` (autouse): the send activities open
  sessions on *this test's* `db_session` connection (savepoints), exactly
  like `app/workflows/tests/conftest.py` does for the pipeline, so their
  writes are visible to assertions and roll back with the test.
- `temporal_env` (session): a time-skipping `WorkflowEnvironment`.
- `send_queue`: a unique task queue per test; `POST /send` is pointed at it
  and `run_send_worker` runs the *real* workflow + activities on it.
- `temporal_client_override`: `get_temporal_client` -> the test env client.
- `smtp_outbox`: records every SMTP hand-off instead of talking to a
  server (the AC1 test uses the real Mailpit instead).

Tests never query `db_session` while a workflow is running (they await the
workflow result first): activities share the connection, and two
concurrent operations on one asyncpg connection fail.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.features.notifications.email import service as email_service
from app.features.notifications.email.service import EmailAttachment
from app.features.quotes.delivery import service as delivery_service
from app.workflows import db as workflow_db
from app.workflows.client import get_temporal_client
from app.workflows.send_activities import SEND_ACTIVITIES
from app.workflows.send_quote_package import SendQuotePackageWorkflow


@pytest_asyncio.fixture(autouse=True)
async def bind_activities_to_test_session(
    monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
    conn = db_session.bind

    def _factory() -> AsyncSession:
        return AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    monkeypatch.setattr(workflow_db, "session_factory", _factory)


@pytest_asyncio.fixture(scope="session")
async def temporal_env() -> AsyncIterator[WorkflowEnvironment]:
    env = await WorkflowEnvironment.start_time_skipping()
    yield env
    await env.shutdown()


@pytest.fixture
def send_queue(monkeypatch: pytest.MonkeyPatch) -> str:
    queue = f"cq020-test-{uuid.uuid4().hex}"
    monkeypatch.setattr(delivery_service, "APPLICATION_PIPELINE_TASK_QUEUE", queue)
    return queue


@pytest.fixture
def temporal_client_override(app: FastAPI, temporal_env: WorkflowEnvironment) -> Iterator[Client]:
    async def _override() -> Client:
        return temporal_env.client

    app.dependency_overrides[get_temporal_client] = _override
    yield temporal_env.client
    app.dependency_overrides.pop(get_temporal_client, None)


def build_send_worker(
    client: Client, queue: str, activities: Sequence[Callable[..., Any]] | None = None
) -> Worker:
    return Worker(
        client,
        task_queue=queue,
        workflows=[SendQuotePackageWorkflow],
        activities=list(activities if activities is not None else SEND_ACTIVITIES),
        # No sticky workflow cache: when AC5's first worker goes away, the
        # next workflow task must go straight to the shared queue instead of
        # waiting out the dead worker's sticky-queue timeout (which the
        # time-skipping test server doesn't skip). Every workflow task then
        # replays the history from scratch -- the restart AC5 is about.
        max_cached_workflows=0,
    )


@pytest.fixture
def run_send_worker(temporal_env: WorkflowEnvironment, send_queue: str) -> Any:
    @asynccontextmanager
    async def _run(
        activities: Sequence[Callable[..., Any]] | None = None,
    ) -> AsyncIterator[Worker]:
        worker = build_send_worker(temporal_env.client, send_queue, activities)
        async with worker:
            yield worker

    return _run


@dataclass
class SentMail:
    to: str
    subject: str
    html: str
    text: str | None
    attachments: list[EmailAttachment] = field(default_factory=list)


@pytest.fixture
def smtp_outbox(monkeypatch: pytest.MonkeyPatch) -> list[SentMail]:
    sent: list[SentMail] = []

    async def _fake_smtp_send(
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
        attachments: Sequence[EmailAttachment] = (),
    ) -> None:
        sent.append(SentMail(to, subject, html, text, list(attachments)))

    monkeypatch.setattr(email_service, "smtp_send", _fake_smtp_send)
    return sent
