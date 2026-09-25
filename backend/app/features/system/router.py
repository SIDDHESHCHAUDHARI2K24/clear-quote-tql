"""System feature routes: `GET /health`.

`router` is included twice by `main.create_app()`: once unprefixed at the
app root (the pinned `/health` contract) and once under `/api/v1` as a side
effect of the generic `FEATURE_ROUTERS` registry loop (see plan.md decision
1) — both point at the same handler.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.features.system.schemas import HealthReport
from app.features.system.service import run_health_checks

router = APIRouter()


@router.get("/health", response_model=HealthReport)
async def get_health(response: Response, db: AsyncSession = Depends(get_db)) -> HealthReport:
    report = await run_health_checks(db)
    if report.status != "ok":
        response.status_code = 503
    return report
