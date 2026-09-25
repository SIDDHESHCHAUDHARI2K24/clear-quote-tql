"""`GET /api/v1/dashboard` (CQ-025 spec.md): the LO console landing page."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff
from app.core.db import get_db
from app.features.dashboard.schemas import DashboardResponse
from app.features.dashboard.service import build_dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    user: CurrentStaff,
    lo_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """An LO always sees their own files (`lo_id` is ignored for them); a
    Manager/Admin sees every file, or just one LO's when `lo_id` is set
    (`core.auth.scope_applications`)."""
    return await build_dashboard(db, user, lo_id)
