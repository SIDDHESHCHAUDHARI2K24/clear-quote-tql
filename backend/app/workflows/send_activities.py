"""Temporal activities for `SendQuotePackageWorkflow` (CQ-020).

Thin wrappers: each opens its own session (`workflow_db.session_factory`,
same as the pipeline activities) and calls the matching idempotent step in
`app.features.quotes.delivery.steps`. Inputs and outputs are strings so
Temporal's JSON converter carries them without custom types.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from temporalio import activity

from app.features.quotes.delivery import steps
from app.workflows import db as workflow_db


@activity.defn
async def freeze_package(package_id: str, workflow_id: str) -> str:
    async with workflow_db.session_factory() as db:
        version_id = await steps.freeze(db, uuid.UUID(package_id), workflow_id)
    return str(version_id)


@activity.defn
async def render_letter_pdf(version_id: str, workflow_id: str) -> str:
    async with workflow_db.session_factory() as db:
        return await steps.render_letter(db, uuid.UUID(version_id), workflow_id)


@activity.defn
async def email_borrower(version_id: str, workflow_id: str) -> str:
    async with workflow_db.session_factory() as db:
        outbox_id = await steps.email_borrower(db, uuid.UUID(version_id), workflow_id)
    return str(outbox_id)


@activity.defn
async def record_send(version_id: str, workflow_id: str) -> None:
    async with workflow_db.session_factory() as db:
        await steps.record(db, uuid.UUID(version_id), workflow_id)


@activity.defn
async def mark_send_failed(package_id: str, workflow_id: str, message: str) -> None:
    async with workflow_db.session_factory() as db:
        await steps.mark_failed(db, uuid.UUID(package_id), workflow_id, message)


SEND_ACTIVITIES: list[Callable[..., Any]] = [
    freeze_package,
    render_letter_pdf,
    email_borrower,
    record_send,
    mark_send_failed,
]
