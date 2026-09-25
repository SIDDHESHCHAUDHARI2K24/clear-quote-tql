"""Seam onto CQ-013's pricing/enrichment service functions.

**Phase A (this session, orchestrator directive):** CQ-013 has not merged
into `phase-p0-p1` yet, so the imports below fail and `PRICING_AVAILABLE` is
`False`. `seed/loader.py` calls `run_pricing_stage` unconditionally for every
persona; when it returns `None`, the loader leaves the application at
whatever status CQ-012's verification produced (`ready_to_price` or
`needs_attention`) and records that the pricing stage was skipped. This is
the "clearly marked seam" the orchestrator's plan calls for -- this module
implements **no** pricing/enrichment logic of its own (that would duplicate
CQ-013's owned calculation and is explicitly out of CQ-010's scope).

**Phase B (after CQ-013 merges):** flip `SEED_SKIP_PRICING=0` (or just rerun
`make demo-reset` once the merge lands) and this module calls CQ-013's real
functions by the exact names CQ-011's spec.md "Contracts" table pins them
at, in the same order the Temporal workflow will later run them. The
`draft_default_quote_set` call signature below is a best-effort guess
(CQ-013 isn't merged to check against) -- reconcile it against the real
signature when wiring Phase B and log a `Decision:` in plan.md if it moved.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

PRICING_AVAILABLE: bool

try:
    from app.features.pricing.enrichment.service import (  # type: ignore[import-not-found]
        enrich_pricing_fields,
        validate_ob_required_fields,
    )
    from app.features.pricing.scenarios.service import auto_price  # type: ignore[import-not-found]
    from app.features.quotes.builder.service import (  # type: ignore[import-not-found]
        draft_default_quote_set,
    )

    PRICING_AVAILABLE = True
except ImportError:
    PRICING_AVAILABLE = False


@dataclass
class PricingStageResult:
    enrichment_result: Any
    pricing_result: Any
    quote_set_result: Any


async def run_pricing_stage(
    application_id: uuid.UUID, db: AsyncSession
) -> PricingStageResult | None:
    """Runs enrich -> validate -> auto_price -> draft_default_quote_set, in
    the order CQ-011's `ApplicationPipelineWorkflow` will later run them,
    calling each CQ-013 function by its pinned name unchanged. Returns
    `None` when CQ-013 is not merged (`PRICING_AVAILABLE` is `False`) --
    the caller must treat that as "pricing stage skipped", not an error.
    """
    if not PRICING_AVAILABLE:
        return None

    enrichment_result = await enrich_pricing_fields(application_id, db)
    await validate_ob_required_fields(application_id, db)
    pricing_result = await auto_price(application_id, db)
    quote_set_result = await draft_default_quote_set(application_id, pricing_result, db)
    return PricingStageResult(
        enrichment_result=enrichment_result,
        pricing_result=pricing_result,
        quote_set_result=quote_set_result,
    )
