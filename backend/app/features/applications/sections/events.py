"""Activity events written by the verification tabs (plan.md Decision #7).

Every payload carries a human-readable `message` (CQ-029's timeline shows
it) plus the `field_key` or `collection`/`row_id` it is about. Values of
sensitive fields (SSN, DOB) are never written into a payload.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.features.applications.timeline.models import ActivityEvent

SYSTEM_ACTOR = "system"

FIELD_EDITED = "field.edited"
FIELD_REVERTED = "field.reverted"
FIELD_AUTO_UPDATED = "field.auto_updated"
ROW_ADDED = "row.added"
FLAG_RAISED = "flag.raised"
FLAG_RESOLVED = "flag.resolved"
SSN_REVEALED = "ssn.revealed"
LIABILITIES_IMPORTED = "credit.liabilities_imported"
HARD_PULL_REQUESTED = "credit.hard_pull_requested"
PROPERTY_UPDATED = "property.updated"
DOCUMENT_RECEIVED = "document.received"
RESUME_REQUESTED = "pipeline.resume_requested"
RESUME_FAILED = "pipeline.resume_failed"


def actor_for(user_id: uuid.UUID | None) -> str:
    return str(user_id) if user_id is not None else SYSTEM_ACTOR


def add_event(
    db: AsyncSession,
    application_id: uuid.UUID,
    *,
    actor: str,
    type: str,
    payload: dict[str, Any],
) -> ActivityEvent:
    """Adds one `activity_events` row. Does not commit."""
    event = ActivityEvent(
        application_id=application_id, actor=actor, type=type, payload=payload, at=now()
    )
    db.add(event)
    return event


async def record_field_event(
    db: AsyncSession,
    application_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    reverted: bool,
    field_key: str,
    label: str | None = None,
) -> None:
    """Hook for the pricing `/field-values` override/revert routes (plan.md
    Decision #6): one event naming the field, then commit."""
    name = label or field_key
    add_event(
        db,
        application_id,
        actor=actor_for(user_id),
        type=FIELD_REVERTED if reverted else FIELD_EDITED,
        payload={
            "field_key": field_key,
            "message": f"Reverted {name} to source" if reverted else f"Edited {name}",
        },
    )
    await db.commit()
