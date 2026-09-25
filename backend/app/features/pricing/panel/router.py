"""`GET /applications/{id}/pricing` route (CQ-017 spec.md)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_scoped_application
from app.core.db import get_db
from app.features.applications.models import Application
from app.features.pricing.panel.schemas import PricingViewResponse
from app.features.pricing.panel.service import get_pricing_view

router = APIRouter(tags=["pricing"])


@router.get("/applications/{application_id}/pricing", response_model=PricingViewResponse)
async def get_pricing(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> PricingViewResponse:
    return await get_pricing_view(db, application)
