"""Request/response schemas for the pricing/scenarios routes.

`QuotePreviewRequest`/`QuotePreviewResponse` are literally CQ-008's
`ScenarioInputs`/`QuoteComputation` (spec.md: "= ScenarioInputs fields" /
"= QuoteComputation fields") -- subclassing keeps them byte-for-byte in sync
with the engine's contract instead of hand-copying every field.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.features.pricing.engine.types import QuoteComputation, ScenarioInputs, StrategyType


class QuotePreviewRequest(ScenarioInputs):
    pass


class QuotePreviewResponse(QuoteComputation):
    pass


class ScenarioCreateRequest(BaseModel):
    """The LO-owned pricing inputs (system-design's "only inputs the LO
    owns" table) minus note rate, which is chosen per-quote, not at
    scenario-creation time. FICO, tax, insurance, HOA and rent/STR are
    enrichment-owned and read from `field_values` server-side."""

    purchase_price: Decimal
    down_payment_pct: Decimal
    strategy: StrategyType
    prepayment_penalty_years: int | None = None
    """Investment only; system-design default is 5 years."""
    label: str | None = None


class PricedProductRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    investor_name: str
    product_name: str
    lock_period_days: int
    note_rate: Decimal
    price_pct: Decimal
    discount_points_pct: Decimal
    discount_points_amount: Decimal
    is_par_rate: bool
    is_buydown_rate: bool


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scenario_id: uuid.UUID
    investor: str
    product: str
    rate: Decimal
    points: Decimal
    lock_days: int
    computed: dict | list | str | float | bool | None
    label: str
    priced_at: datetime
    created_at: datetime
    updated_at: datetime


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    inputs: dict | list | str | float | bool | None
    config_snapshot: dict | list | str | float | bool | None
    dscr_bucket: str | None
    quotes: list[QuoteRead]


class AutoQuoteResponse(BaseModel):
    par: QuoteRead
    buydown: QuoteRead | None


class ManualQuoteCreateRequest(BaseModel):
    product: PricedProductRow
    label: str
