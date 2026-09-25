"""Seam onto CQ-013's pricing/enrichment service functions.

**Phase B (CQ-013 merged into `phase-p0-p1` as of `a95498b`):** calls the
real functions by the exact names and argument order CQ-013 actually ships
(confirmed by reading `pricing/enrichment/service.py`, `pricing/scenarios/
service.py` and `quotes/builder/service.py` directly -- all four take
`(db, application_id, ...)`, not `(application_id, db, ...)` as this
module's Phase A guess had it). No pricing/enrichment logic lives here --
this module only sequences CQ-013's own calls in the order CQ-011's
workflow will later run them.

Raises whatever CQ-009/CQ-013 raise (`PricingValidationError`,
`ProviderUnavailableError`, `ValidationAppError`, ...) -- the caller
(`seed/loader.py`) decides how a raised error maps onto `application_status`
(matches CQ-011's own "on failure -> needs_attention" contract for these
same four stages).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.pricing.enrichment.service import (
    EnrichmentResult,
    enrich_pricing_fields,
    validate_ob_required_fields,
)
from app.features.pricing.scenarios.service import PricingResult, auto_price
from app.features.quotes.builder.service import QuoteSetResult, draft_default_quote_set


@dataclass
class PricingStageResult:
    enrichment_result: EnrichmentResult
    pricing_result: PricingResult
    quote_set_result: QuoteSetResult


async def run_pricing_stage(db: AsyncSession, application_id: uuid.UUID) -> PricingStageResult:
    """Runs enrich -> validate -> auto_price -> draft_default_quote_set, in
    the order CQ-011's `ApplicationPipelineWorkflow` will later run them,
    calling each CQ-013 function by its pinned name/signature unchanged.
    Propagates any exception CQ-013/CQ-009 raise (e.g. `PricingValidation
    Error` for Aisha Coleman's missing-field case) -- the caller handles it.
    """
    enrichment_result = await enrich_pricing_fields(db, application_id)
    await validate_ob_required_fields(db, application_id)
    pricing_result = await auto_price(db, application_id)
    quote_set_result = await draft_default_quote_set(db, application_id, pricing_result)
    return PricingStageResult(
        enrichment_result=enrichment_result,
        pricing_result=pricing_result,
        quote_set_result=quote_set_result,
    )
