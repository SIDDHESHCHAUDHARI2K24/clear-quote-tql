"""`GET /applications/{id}/pricing` response shape (CQ-017 spec.md).

Every money/rate number reachable from `breakdown` is `quote_engine` output
(`QuoteComputation`, byte-for-byte the same type `/quotes/preview` returns)
-- the frontend never recomputes any of it (AGENTS.md: money math lives
only in `quote_engine`).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.enums import FieldSource
from app.features.pricing.engine.types import QuoteComputation, StrategyType


class PricingFieldView(BaseModel):
    """One of the 5 pricing-overridable `field_values` rows (spec.md:
    taxes, insurance, HOA, LTR rent / STR revenue), with enough to render a
    `SourceBadge` and an inline override/revert control."""

    model_config = ConfigDict(frozen=True)

    field_key: str
    value: Decimal | str | None
    source: FieldSource
    source_ref: str | None
    overridden: bool
    original_value: Decimal | str | None
    """The value the field's own source adapter would return right now --
    only ever populated when `overridden` is true (there is no stored
    pre-override snapshot; see plan.md Decision 7). `None` when not
    overridden (the current `value` already *is* the source value)."""


class PricingInputsView(BaseModel):
    """The raw, non-badge-carrying pieces `/quotes/preview` also needs but
    that don't appear in `PricingFieldView` (FICO has no source badge in
    spec.md's field list; `insurance_annual_rate` is a rate the engine
    consumes, derived server-side from `homeowners_ins_annual` -- the panel
    only ever shows the dollar `homeowners_ins_annual` badge/value, never
    this fraction, but every future preview call still needs to send it, so
    it's handed over ready-computed rather than making the frontend divide
    two money fields itself)."""

    model_config = ConfigDict(frozen=True)

    purchase_price: Decimal
    down_payment_pct: Decimal
    strategy: StrategyType
    prepayment_penalty_years: int | None
    fico: int | None
    insurance_annual_rate: Decimal | None


class PricingViewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    application_id: uuid.UUID
    inputs: PricingInputsView
    fields: list[PricingFieldView]
    note_rate: Decimal | None
    """The current scenario's own priced rate (0-1 fraction, same scale as
    `ScenarioInputs.note_rate`) -- the recommended quote's rate once CQ-018
    sets one, else the current scenario's own Par quote (plan.md Decision
    5). `None` until at least one quote has been priced for this
    application."""
    breakdown: QuoteComputation | None
    """`None` when nothing has been priced yet (no scenario/quote) or the
    current scenario's inputs can't be priced (e.g. `LtvOutOfRangeError`)."""
    has_stale_quotes: bool
