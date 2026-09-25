"""`GET /api/v1/portal/reports/{token}` (CQ-022 spec.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentBorrower
from app.core.db import get_db

from . import service
from .schemas import PortalReportResponse

router = APIRouter(prefix="/portal/reports", tags=["portal-reports"])


@router.get("/{token}", response_model=PortalReportResponse)
async def get_report(
    token: str,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> PortalReportResponse:
    return await service.get_report_for_token(db, token=token, borrower=borrower)
