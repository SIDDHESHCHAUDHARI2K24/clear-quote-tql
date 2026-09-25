"""Pricing/scenarios routes (spec.md route table)."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, get_scoped_application
from app.core.db import get_db
from app.core.errors import ValidationAppError
from app.features.applications.locks import lock_application
from app.features.applications.models import Application
from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot
from app.features.pricing.scenarios.deps import ensure_scenario_in_scope
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
    compute_for_product,
    create_manual_quote,
    create_scenario,
    find_offered_product,
    get_priced_products_for_scenario,
    get_scenario,
    rebuild_scenario_inputs,
    tag_par_and_buydown,
)
from app.features.quotes.builder.service import (
    autoquote_replacing,
    ensure_priceable,
    missing_field_error,
)
from app.integrations.common.errors import PricingValidationError

router = APIRouter(tags=["pricing"])


@router.post("/quotes/preview", response_model=QuotePreviewResponse)
async def preview_quote(
    request: QuotePreviewRequest,
    _user: CurrentStaff,
) -> QuotePreviewResponse:
    """Engine-only, no adapter latency, no persistence -- must respond
    under 300ms (spec.md AC1). CQ-017: requires a signed-in staff user
    (was previously reachable with no auth at all -- this route computes
    real numbers for real applications, unlike `/scenarios/{id}/products`
    which already required `CurrentStaff` via `ensure_scenario_in_scope`);
    not scoped to any one application since it's a pure engine call with
    no persistence."""
    computation = compute_quote(request, ConfigSnapshot())
    return QuotePreviewResponse.model_validate(computation.model_dump())


@router.post("/applications/{application_id}/scenarios", response_model=ScenarioRead)
async def post_scenario(
    application_id: uuid.UUID,
    request: ScenarioCreateRequest,
    db: AsyncSession = Depends(get_db),
    _application: Application = Depends(get_scoped_application),
) -> ScenarioRead:
    # CQ-018: a missing OB-required field (e.g. Aisha Coleman's Occupancy)
    # 422s as `missing_field` before anything is written.
    await ensure_priceable(db, application_id, request.down_payment_pct)
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
    _scope: None = Depends(ensure_scenario_in_scope),
) -> list[PricedProductRow]:
    try:
        products = await get_priced_products_for_scenario(db, scenario_id)
    except PricingValidationError as exc:
        raise missing_field_error(exc) from exc
    scenario = await get_scenario(db, scenario_id)
    # CQ-018 PR review M3: tag Par/Buydown with AutoQuote's own rule, not
    # the mock's `is_buydown_rate`, so the grid's Buydown is the card's.
    products = tag_par_and_buydown(products)
    return [
        PricedProductRow.model_validate(
            {
                **product.model_dump(),
                "monthly_pi": compute_for_product(scenario, product).monthly_pi,
                "points_pct": (product.discount_points_pct * Decimal("100")).quantize(
                    Decimal("0.001")
                ),
            }
        )
        for product in products
    ]


@router.post("/scenarios/{scenario_id}/autoquote", response_model=AutoQuoteResponse)
async def post_autoquote(
    scenario_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    _scope: None = Depends(ensure_scenario_in_scope),
) -> AutoQuoteResponse:
    # CQ-018 (plan.md Decision 4): Save & AutoQuote *replaces* the
    # scenario's Par/Buydown (was: appended another pair every call).
    par_quote, buydown_quote = await autoquote_replacing(db, scenario_id, user)
    return AutoQuoteResponse(
        par=QuoteRead.model_validate(par_quote),
        buydown=QuoteRead.model_validate(buydown_quote) if buydown_quote is not None else None,
    )


@router.post("/scenarios/{scenario_id}/quotes", response_model=QuoteRead)
async def post_manual_quote(
    scenario_id: uuid.UUID,
    request: ManualQuoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    _scope: None = Depends(ensure_scenario_in_scope),
) -> QuoteRead:
    # CQ-018 PR review (minor 5): the client's row only names the product
    # (investor, product, lock); rate and points come from a fresh grid.
    scenario = await get_scenario(db, scenario_id)
    await lock_application(db, scenario.application_id)
    # Re-read enrichment-owned inputs (tax, insurance, HOA, rent) first: the
    # overlay skips a no-op PUT, so an override since the last save would
    # otherwise price this pick from stale inputs (code review).
    await rebuild_scenario_inputs(db, scenario)
    try:
        products = await get_priced_products_for_scenario(db, scenario_id)
    except PricingValidationError as exc:
        raise missing_field_error(exc) from exc
    picked = request.product
    product = find_offered_product(
        products, picked.investor_name, picked.product_name, picked.lock_period_days
    )
    if product is None:
        raise ValidationAppError(
            f"{picked.investor_name} {picked.product_name} is no longer offered at these inputs.",
            code="product_not_offered",
            details={"field": "product"},
        )
    quote = await create_manual_quote(db, scenario_id, product, request.label)
    return QuoteRead.model_validate(quote)
