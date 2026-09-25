"""Per-application row lock (CQ-028a review M1).

Every verification-tab write and the pipeline's verify step take the same
`SELECT applications.id ... FOR NO KEY UPDATE` lock, so LO edits and a
running pipeline for one application serialise instead of racing on `flags`
and `field_values`. The lock is held until the caller's transaction ends.

`FOR NO KEY UPDATE` (not `FOR UPDATE`, lock-hardening minor 3): it still
conflicts with itself and with `FOR UPDATE` (CQ-030's `mark_stale`, the
summary PATCH), but not with the `FOR KEY SHARE` lock Postgres takes on
`applications` for every insert of a row that references it
(`activity_events`, `flags`, ...). With `FOR UPDATE`, a holder waiting on
another session that was inserting such a row while waiting for the lock
deadlocked.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import Application


async def lock_application(db: AsyncSession, application_id: uuid.UUID) -> None:
    """Locks the `applications` row until the current transaction ends."""
    await db.execute(
        select(Application.id)
        .where(Application.id == application_id)
        .with_for_update(key_share=True)
    )
