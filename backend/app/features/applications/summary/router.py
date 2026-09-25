"""Workspace summary + status routes (spec.md CQ-016 "Backend")."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, get_scoped_application
from app.core.db import get_db
from app.features.applications.models import Application
from app.features.applications.summary.schemas import ApplicationSummaryResponse, StatusPatchRequest
from app.features.applications.summary.service import (
    build_application_summary,
    patch_application_status,
)

router = APIRouter(tags=["applications"])


@router.get("/applications/{application_id}/summary", response_model=ApplicationSummaryResponse)
async def get_application_summary(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> ApplicationSummaryResponse:
    return await build_application_summary(db, application)


@router.patch("/applications/{application_id}/status", response_model=ApplicationSummaryResponse)
async def patch_status(
    application_id: uuid.UUID,
    request: StatusPatchRequest,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> ApplicationSummaryResponse:
    return await patch_application_status(db, application, request, user.id)
