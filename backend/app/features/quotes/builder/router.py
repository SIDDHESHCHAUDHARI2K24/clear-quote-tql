"""Quote Builder routes (CQ-018): the grouped quote-card read model,
scenario edits, recommend, delete and whole-application reprice.

Save & AutoQuote, the products grid, manual picks and scenario creation
stay on CQ-013's `pricing.scenarios` router (plan.md Decision 1). Every
route is scoped: out-of-scope ids 404 (Decision #11).
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, get_scoped_application
from app.core.db import get_db
from app.features.applications.models import Application
from app.features.pricing.scenarios.deps import ensure_scenario_in_scope
from app.features.quotes.builder.schemas import (
    ApplicationScenariosRead,
    RecommendResponse,
    RepriceResponse,
    ScenarioGroupRead,
    ScenarioUpdateRequest,
)
from app.features.quotes.builder.service import (
    delete_quote,
    get_scoped_quote,
    list_application_scenarios,
    recommend_quote,
    reprice_application,
    update_scenario,
)

router = APIRouter(tags=["quote-builder"])


@router.get("/applications/{application_id}/scenarios", response_model=ApplicationScenariosRead)
async def get_application_scenarios(
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> ApplicationScenariosRead:
    return await list_application_scenarios(db, application)


@router.put("/scenarios/{scenario_id}", response_model=ScenarioGroupRead)
async def put_scenario(
    scenario_id: uuid.UUID,
    request: ScenarioUpdateRequest,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    _scope: None = Depends(ensure_scenario_in_scope),
) -> ScenarioGroupRead:
    return await update_scenario(db, scenario_id, request, user)


@router.delete("/quotes/{quote_id}", status_code=204)
async def delete_quote_route(
    quote_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> Response:
    quote = await get_scoped_quote(db, quote_id, user)
    await delete_quote(db, quote, user)
    return Response(status_code=204)


@router.post("/quotes/{quote_id}/recommend", response_model=RecommendResponse)
async def post_recommend(
    quote_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> RecommendResponse:
    quote = await get_scoped_quote(db, quote_id, user)
    application = await recommend_quote(db, quote, user)
    return RecommendResponse(
        application_id=application.id, recommended_quote_id=application.recommended_quote_id
    )


@router.post("/applications/{application_id}/reprice", response_model=RepriceResponse)
async def post_reprice(
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> RepriceResponse:
    return await reprice_application(db, application, user)
