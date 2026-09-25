"""`GET /api/v1/portal/me` (CQ-031 spec.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentBorrower
from app.core.db import get_db

from . import service
from .schemas import PortalHomeResponse

router = APIRouter(prefix="/portal", tags=["portal-home"])


@router.get("/me", response_model=PortalHomeResponse)
async def get_portal_home(
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> PortalHomeResponse:
    return await service.get_home(db, borrower=borrower)
