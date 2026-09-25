"""Request/response schemas for the Quote Builder routes (CQ-018).

Every money/rate figure on a card is copied from that quote's stored engine
output (`Quote.computed`) or scaled to a display percent server-side --
the LO Console only formats these strings, never computes (AGENTS.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.features.pricing.engine.types import DSCRBucket


class QuoteCardRead(BaseModel):
    id: uuid.UUID
    scenario_id: uuid.UUID
    label: str
    """`Par` / `Buydown` / `Manual`."""
    investor: str
    product: str
    rate_pct: str
    """Note rate, percent scale, 3dp (e.g. `"7.625"`)."""
    points_pct: str
    """Discount points, percent scale, 3dp; negative = lender credit."""
    points_amount: str
    """`computed.discount_points_amount` (negative = credit)."""
    note_rate: str
    """Engine scale (0-1 fraction) of `rate_pct`, for `/quotes/preview`."""
    discount_points_pct: str
    """Engine scale (0-1 fraction) of `points_pct`, for `/quotes/preview`."""
    lock_days: int
    monthly_payment: str
    """`computed.total_monthly_payment`."""
    cash_to_close: str
    """`computed.cash_to_close`."""
    down_payment_pct: str
    """Display percent, 2dp (e.g. `"20.00"`)."""
    prepay_label: str | None
    """Investment only (e.g. `"5-year prepay"`); `None` for primary."""
    dscr_ratio: str | None
    """Investment only; always `None` for primary."""
    monthly_cashflow: str | None
    """Investment only; always `None` for primary."""
    priced_at: datetime
    stale: bool
    recommended: bool
    computed: dict[str, object]
    """The full engine output, unchanged."""


class ScenarioInputsRead(BaseModel):
    purchase_price: str
    down_payment_pct: str
    """0-1 fraction, as stored (e.g. `"0.20"`)."""
    prepayment_penalty_years: int | None
    lock_days: int
    fico: int
    strategy: Literal["PRIMARY", "LTR", "STR"]


class ScenarioGroupRead(BaseModel):
    id: uuid.UUID
    label: str
    """Server-built group heading, e.g. `"At DSCR 1.00"`,
    `"At your DSCR (0.69)"`, `"At 5% down"`."""
    note: str | None
    """`"Your DSCR prices the same as 1.00"` for a collapsed investment set."""
    dscr_bucket: DSCRBucket | None
    """Assumed DSCR bucket priced at (investment only)."""
    inputs: ScenarioInputsRead
    engine_inputs: dict[str, object]
    """The scenario's full stored `ScenarioInputs` JSON (engine scale), so
    the overlay's live preview can post it to `/quotes/preview` unchanged
    apart from the edited LO inputs."""
    quotes: list[QuoteCardRead]
    created_at: datetime


class ApplicationScenariosRead(BaseModel):
    application_id: uuid.UUID
    strategy: Literal["PRIMARY", "LTR", "STR"] | None
    """`None` when occupancy/strategy is unknown (e.g. Aisha Coleman)."""
    recommended_quote_id: uuid.UUID | None
    groups: list[ScenarioGroupRead]


class ScenarioUpdateRequest(BaseModel):
    """`PUT /scenarios/{id}` -- the LO-owned inputs the overlay edits.
    Enrichment-owned inputs (FICO, tax, insurance, HOA, rent) are always
    re-read from `field_values` server-side."""

    purchase_price: Decimal = Field(gt=0)
    down_payment_pct: Decimal = Field(gt=0, lt=1)
    prepayment_penalty_years: int | None = Field(default=None, ge=0, le=5)
    """Investment only; ignored (stored as-is) for primary."""
    lock_days: int = Field(default=30, ge=15, le=90)
    dscr_bucket: DSCRBucket | None = None
    """Investment only: the assumed DSCR bucket to price at. `None` keeps
    the scenario's current bucket."""


class RepriceResponse(BaseModel):
    application_id: uuid.UUID
    quote_ids: list[uuid.UUID]
    priced_at: datetime


class RecommendResponse(BaseModel):
    application_id: uuid.UUID
    recommended_quote_id: uuid.UUID | None
