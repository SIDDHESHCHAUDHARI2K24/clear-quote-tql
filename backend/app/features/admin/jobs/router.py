"""Admin job triggers (CQ-030). `POST /api/v1/admin/jobs/stale-check` runs
the same `mark_stale` the scheduled Temporal activity runs, in-process, at
`core/clock.now()`. Admin only: other roles get 403 through
`require_roles` (E16)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.auth import require_roles
from app.core.db import get_db
from app.core.enums import UserRole
from app.features.admin.jobs.schemas import StaleCheckResponse
from app.features.auth.models import User
from app.features.quotes.stale.service import mark_stale

router = APIRouter(prefix="/admin/jobs", tags=["admin"])


@router.post("/stale-check", response_model=StaleCheckResponse)
async def run_stale_check(
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> StaleCheckResponse:
    now = clock.now()
    result = await mark_stale(db, now)
    await db.commit()
    return StaleCheckResponse(
        ran_at=now,
        quotes_marked_stale=result.quotes_marked_stale,
        versions_expired=result.versions_expired,
        applications_marked_stale=result.applications_marked_stale,
        application_ids=[uuid.UUID(i) for i in result.application_ids],
    )
