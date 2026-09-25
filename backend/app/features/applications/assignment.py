"""LO auto-assignment (P5/P6 foundation, phase-p5-p6-plan.md E15).

`least_loaded_lo_id` is the one rule every "who gets this borrower?"
decision uses: borrower self sign-up (`auth/borrower/service.py`, CQ-015)
and the portal apply wizard's submit (CQ-032 AC5).
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.applications.models import Application
from app.features.auth.models import User

INACTIVE_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED}
)
"""Statuses that no longer count toward an LO's load."""


async def least_loaded_lo_id(db: AsyncSession) -> uuid.UUID | None:
    """The id of the LO (role `lo`) with the fewest *active* applications
    (any status except withdrawn/closed); ties go to the alphabetically
    first `full_name` (then `id`, so the choice is deterministic). `None`
    when there is no LO at all."""
    active_count = func.count(Application.id)
    stmt = (
        select(User.id)
        .select_from(User)
        .outerjoin(
            Application,
            and_(
                Application.lo_id == User.id,
                Application.status.not_in(INACTIVE_STATUSES),
            ),
        )
        .where(User.role == UserRole.LO)
        .group_by(User.id, User.full_name)
        .order_by(active_count, User.full_name, User.id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
