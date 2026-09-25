"""Per-application write lock (CQ-018 PR review, minor 4).

Every Quote Builder write and every CQ-017 field-value override/revert
starts by taking `SELECT ... FOR UPDATE` on the application's row, so
writes to one application's pricing state serialize:

- an override that commits while a reprice is running waits for the
  reprice to commit, then marks the fresh quotes stale (it can't be
  overwritten with `stale=False`);
- two concurrent Save & AutoQuotes on one scenario run one after the
  other, so the second updates the first's Par in place instead of
  inserting a second Par.

The lock is held until the request's transaction commits or rolls back.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.features.applications.models import Application


async def lock_application(db: AsyncSession, application_id: uuid.UUID) -> Application:
    """Locks and re-reads (`populate_existing`) the application row."""
    application = (
        await db.execute(
            select(Application)
            .where(Application.id == application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    return application
