"""`GET /applications/{id}/matches` (spec.md "Backend"). LO auth
(`get_scoped_application` -- out-of-scope returns 404, per Decision #11)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_scoped_application
from app.core.db import get_db
from app.features.applications.models import Application
from app.features.matches.schemas import MatchListResponse, MatchOut
from app.features.matches.service import find_current_matches

router = APIRouter(tags=["matches"])


@router.get("/applications/{application_id}/matches", response_model=MatchListResponse)
async def get_matches(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> MatchListResponse:
    matches = await find_current_matches(db, application)
    return MatchListResponse(matches=[MatchOut.from_input(m) for m in matches])
