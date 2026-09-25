"""`GET /applications/{id}/activity` (spec.md "Timeline"). Staff auth via
`get_scoped_application` -- an LO out of scope gets 404 (Decision #11 /
plan.md E16), same as every other `application_id`-keyed route."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_scoped_application
from app.core.db import get_db
from app.core.pagination import Page
from app.features.applications.models import Application
from app.features.applications.timeline.schemas import ActivityEventOut
from app.features.applications.timeline.service import list_activity

router = APIRouter(tags=["timeline"])


@router.get("/applications/{application_id}/activity", response_model=Page[ActivityEventOut])
async def get_activity(
    application_id: uuid.UUID,
    page: int | None = Query(default=1),
    page_size: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> Page[ActivityEventOut]:
    return await list_activity(db, application, page, page_size)
