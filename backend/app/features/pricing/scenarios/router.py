"""Pricing/scenarios routes (spec.md route table)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot
from app.features.pricing.scenarios.deps import get_current_lo_stub
from app.features.pricing.scenarios.schemas import (
    AutoQuoteResponse,
    ManualQuoteCreateRequest,
    PricedProductRow,
    QuotePreviewRequest,
    QuotePreviewResponse,
    QuoteRead,
    ScenarioCreateRequest,
    ScenarioRead,
)
from app.features.pricing.scenarios.service import (
    autoquote_scenario,
    create_manual_quote,
    create_scenario,
    get_priced_products_for_scenario,
)
from app.integrations.pricing.schemas import PricedProductDTO

router = APIRouter(tags=["pricing"])


@router.post("/quotes/preview", response_model=QuotePreviewResponse)
async def preview_quote(request: QuotePreviewRequest) -> QuotePreviewResponse:
    """Engine-only, no adapter latency, no persistence -- must respond
    under 300ms (spec.md AC1)."""
    computation = compute_quote(request, ConfigSnapshot())
    return QuotePreviewResponse.model_validate(computation.model_dump())


@router.post("/applications/{application_id}/scenarios", response_model=ScenarioRead)
async def post_scenario(
    application_id: uuid.UUID,
    request: ScenarioCreateRequest,
    db: AsyncSession = Depends(get_db),
    lo_id: uuid.UUID = Depends(get_current_lo_stub),
) -> ScenarioRead:
    scenario = await create_scenario(
        db,
        application_id,
        request.purchase_price,
        request.down_payment_pct,
        request.strategy,
        request.prepayment_penalty_years,
    )
    return ScenarioRead(
        id=scenario.id,
        application_id=scenario.application_id,
        inputs=scenario.inputs,
        config_snapshot=scenario.config_snapshot,
        dscr_bucket=scenario.dscr_bucket,
        quotes=[],
    )


@router.get("/scenarios/{scenario_id}/products", response_model=list[PricedProductRow])
async def get_products(
    scenario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    lo_id: uuid.UUID = Depends(get_current_lo_stub),
) -> list[PricedProductRow]:
    products = await get_priced_products_for_scenario(db, scenario_id)
    return [PricedProductRow.model_validate(product.model_dump()) for product in products]


@router.post("/scenarios/{scenario_id}/autoquote", response_model=AutoQuoteResponse)
async def post_autoquote(
    scenario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    lo_id: uuid.UUID = Depends(get_current_lo_stub),
) -> AutoQuoteResponse:
    par_quote, buydown_quote = await autoquote_scenario(db, scenario_id)
    return AutoQuoteResponse(
        par=QuoteRead.model_validate(par_quote),
        buydown=QuoteRead.model_validate(buydown_quote) if buydown_quote is not None else None,
    )


@router.post("/scenarios/{scenario_id}/quotes", response_model=QuoteRead)
async def post_manual_quote(
    scenario_id: uuid.UUID,
    request: ManualQuoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    lo_id: uuid.UUID = Depends(get_current_lo_stub),
) -> QuoteRead:
    product = PricedProductDTO(**request.product.model_dump())
    quote = await create_manual_quote(db, scenario_id, product, request.label)
    return QuoteRead.model_validate(quote)
