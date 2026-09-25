"""`GET /admin/settings` (spec.md "Settings"). Admin only."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.db import get_db
from app.core.enums import UserRole
from app.features.admin.settings.schemas import SettingsResponse
from app.features.admin.settings.service import list_settings

router = APIRouter(prefix="/admin", tags=["admin"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings_page(
    _admin: object = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
) -> SettingsResponse:
    return SettingsResponse(settings=await list_settings(db))
