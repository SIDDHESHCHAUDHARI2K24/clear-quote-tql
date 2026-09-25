"""`run_two_pass_dscr`: the DSCR pricing loop (system-design.md § Calculation
engine, spec.md).

Pass 1 prices at the caller-supplied assumed bucket (default `ONE_TO_1_25`,
i.e. DSCR 1.00 sent to OB); `compute_quote` gives the actual DSCR/bucket for
that par product's rate. If the actual bucket differs, pass 2 re-prices at
the actual bucket. Max 2 passes -- if pass 2's own actual bucket differs
again (flip-flop), the lower-DSCR result is kept and a `warning` `flags` row
is written (`info` never produces a `flags` row, per CQ-007).

`price_par_at_dscr` is a caller-supplied callback (not a direct
`PricingClient` call) so this stays a small, pure-ish unit testable without
a DB/OB round trip (spec.md AC8); production callers close over the real
mock call + `build_ob_search_request`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity
from app.features.applications.verification.service import resolve_flag, write_flag
from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import (
    ConfigSnapshot,
    DSCRBucket,
    QuoteComputation,
    ScenarioInputs,
)
from app.integrations.pricing.schemas import PricedProductDTO

DSCR_BUCKET_UNSTABLE_RULE = "dscr_bucket_unstable"

# Representative DSCR value sent to OB per assumed bucket (the mock rate
# sheet only keys off `bucket_for_dscr(request.DSCR)`, so any value in the
# bucket prices identically -- see plan.md Decision 12).
ASSUMED_DSCR_BY_BUCKET: dict[DSCRBucket, Decimal] = {
    DSCRBucket.BELOW_1_00: Decimal("0.99"),
    DSCRBucket.ONE_TO_1_25: Decimal("1.00"),
    DSCRBucket.GE_1_25: Decimal("1.25"),
}

PricePricer = Callable[[Decimal], Awaitable[PricedProductDTO]]


@dataclass(frozen=True)
class TwoPassDscrResult:
    computation: QuoteComputation
    passes: int
    bucket_flipped: bool
    par_product: PricedProductDTO
    priced_at_dscr: Decimal
    """The DSCR value actually sent to OB for the *kept* pass -- callers
    that need the rest of that pass's rate-sheet grid (e.g. to pick a
    buydown row alongside this par) must re-fetch at this exact value, not
    at `computation.dscr_bucket`'s own representative value, since a
    flipped/kept-lower-DSCR pass's actual bucket can differ from what was
    assumed for it."""


def inputs_with_priced_product(inputs: ScenarioInputs, product: PricedProductDTO) -> ScenarioInputs:
    # `PricedProductDTO.note_rate` is percent-scale (e.g. `7.125` meaning
    # 7.125%, matching `provider_rate_sheet.base_rate`); `ScenarioInputs.
    # note_rate` is a 0-1 fraction like every other engine rate field.
    # `discount_points_pct` is already a fraction on both sides (no
    # conversion) -- see `MockPricingClient._price_rows`.
    return inputs.model_copy(
        update={
            "note_rate": product.note_rate / Decimal("100"),
            "discount_points_pct": product.discount_points_pct,
        }
    )


async def run_two_pass_dscr(
    db: AsyncSession,
    application_id: uuid.UUID,
    base_inputs: ScenarioInputs,
    config: ConfigSnapshot,
    price_par_at_dscr: PricePricer,
    assumed_bucket: DSCRBucket = DSCRBucket.ONE_TO_1_25,
) -> TwoPassDscrResult:
    par_1 = await price_par_at_dscr(ASSUMED_DSCR_BY_BUCKET[assumed_bucket])
    computation_1 = compute_quote(inputs_with_priced_product(base_inputs, par_1), config)
    actual_bucket_1 = computation_1.dscr_bucket
    assert actual_bucket_1 is not None  # LTR/STR always populates dscr_bucket

    if actual_bucket_1 == assumed_bucket:
        await resolve_flag(db, application_id, "dscr_ratio", DSCR_BUCKET_UNSTABLE_RULE)
        return TwoPassDscrResult(
            computation=computation_1,
            passes=1,
            bucket_flipped=False,
            par_product=par_1,
            priced_at_dscr=ASSUMED_DSCR_BY_BUCKET[assumed_bucket],
        )

    assert computation_1.dscr_ratio is not None
    par_2 = await price_par_at_dscr(ASSUMED_DSCR_BY_BUCKET[actual_bucket_1])
    computation_2 = compute_quote(inputs_with_priced_product(base_inputs, par_2), config)
    actual_bucket_2 = computation_2.dscr_bucket
    assert actual_bucket_2 is not None

    if actual_bucket_2 == actual_bucket_1:
        await resolve_flag(db, application_id, "dscr_ratio", DSCR_BUCKET_UNSTABLE_RULE)
        return TwoPassDscrResult(
            computation=computation_2,
            passes=2,
            bucket_flipped=False,
            par_product=par_2,
            priced_at_dscr=ASSUMED_DSCR_BY_BUCKET[actual_bucket_1],
        )

    # Flip-flop: pass 2's own actual bucket disagrees with what it assumed.
    # Stop at 2 passes and keep the lower-DSCR result.
    assert computation_2.dscr_ratio is not None
    if computation_1.dscr_ratio <= computation_2.dscr_ratio:
        kept_computation, kept_product, kept_dscr = (
            computation_1,
            par_1,
            ASSUMED_DSCR_BY_BUCKET[assumed_bucket],
        )
    else:
        kept_computation, kept_product, kept_dscr = (
            computation_2,
            par_2,
            ASSUMED_DSCR_BY_BUCKET[actual_bucket_1],
        )

    await write_flag(
        db,
        application_id,
        ApplicationTab.PRICING,
        "dscr_ratio",
        DSCR_BUCKET_UNSTABLE_RULE,
        FlagSeverity.WARNING,
    )
    return TwoPassDscrResult(
        computation=kept_computation,
        passes=2,
        bucket_flipped=True,
        par_product=kept_product,
        priced_at_dscr=kept_dscr,
    )
