"""Send tab routes (CQ-019): the draft package, its readiness, the borrower
report preview and the pre-approval letter preview. Every route is scoped:
an out-of-scope application or package 404s (Decision #11)."""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, get_scoped_application
from app.core.db import get_db
from app.features.applications.models import Application
from app.features.quotes.pdf.service import render_package_letter
from app.features.quotes.report.schemas import ReportViewModel
from app.features.quotes.send.schemas import PackageRead, PackageReadiness, PackageUpdate
from app.features.quotes.send.service import (
    get_or_create_package,
    get_scoped_package,
    package_read,
    package_readiness,
    package_report,
    update_package,
)

router = APIRouter(tags=["send"])

LETTER_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
"""The letter never runs script, even when opened directly (plan.md
Decision 17); the Send tab also renders it in `<iframe sandbox="">`."""


@router.get("/applications/{application_id}/package", response_model=PackageRead)
async def get_package(
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> PackageRead:
    package = await get_or_create_package(db, application)
    return await package_read(db, package)


@router.put("/applications/{application_id}/package", response_model=PackageRead)
async def put_package(
    body: PackageUpdate,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> PackageRead:
    package = await update_package(db, application, body, user)
    return await package_read(db, package)


@router.get("/packages/{package_id}/readiness", response_model=PackageReadiness)
async def get_readiness(
    package_id: uuid.UUID, user: CurrentStaff, db: AsyncSession = Depends(get_db)
) -> PackageReadiness:
    package = await get_scoped_package(db, package_id, user)
    return await package_readiness(db, package)


@router.get("/packages/{package_id}/report", response_model=ReportViewModel)
async def get_report(
    package_id: uuid.UUID, user: CurrentStaff, db: AsyncSession = Depends(get_db)
) -> ReportViewModel:
    package = await get_scoped_package(db, package_id, user)
    return await package_report(db, package)


@router.get("/packages/{package_id}/letter.html", response_class=HTMLResponse)
async def get_letter_html(
    package_id: uuid.UUID, user: CurrentStaff, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    package = await get_scoped_package(db, package_id, user)
    html = await render_package_letter(db, package)
    return HTMLResponse(
        html, headers={"Content-Security-Policy": LETTER_CSP, "Cache-Control": "no-store"}
    )
