"""`draft_default_quote_set`: the exact function name CQ-011's `draft_quote_
set` activity calls to wrap up the automated pipeline's last stage.

Per plan.md Decision 11: no new persisted "quote set"/recommendation table
is in CQ-007's model list for this item -- `quote_packages.
recommended_quote_id` is CQ-019/22's Send-tab job, built later from whatever
quotes the LO actually sends. This function's job here is a thin
confirmation: it loads every `Quote` row `auto_price`'s `PricingResult`
named (proving they exist and belong to this application) and returns them
as the drafted set.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.service import PricingResult
from app.features.quotes.builder.models import Quote


@dataclass(frozen=True)
class QuoteSetResult:
    quote_ids: list[uuid.UUID]


async def draft_default_quote_set(
    db: AsyncSession, application_id: uuid.UUID, pricing_result: PricingResult
) -> QuoteSetResult:
    if not pricing_result.quote_ids:
        return QuoteSetResult(quote_ids=[])
    rows = (
        (
            await db.execute(
                select(Quote.id)
                .join(Scenario, Quote.scenario_id == Scenario.id)
                .where(
                    Scenario.application_id == application_id,
                    Quote.id.in_(pricing_result.quote_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return QuoteSetResult(quote_ids=list(rows))
