"""`POST /api/v1/portal/reports/{token}/actions` (CQ-024 spec.md)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentBorrower
from app.core.db import get_db

from . import service
from .schemas import PortalReportActionRequest, PortalReportActionResponse

router = APIRouter(prefix="/portal/reports", tags=["portal-actions"])


@router.post("/{token}/actions", response_model=PortalReportActionResponse)
async def submit_report_action(
    token: str,
    request: PortalReportActionRequest,
    borrower: CurrentBorrower,
    db: AsyncSession = Depends(get_db),
) -> PortalReportActionResponse:
    return await service.submit_action(db, token=token, borrower=borrower, request=request)
