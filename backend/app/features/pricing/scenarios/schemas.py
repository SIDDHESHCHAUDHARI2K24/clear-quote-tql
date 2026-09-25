"""Request/response schemas for the pricing/scenarios routes.

`QuotePreviewRequest`/`QuotePreviewResponse` are literally CQ-008's
`ScenarioInputs`/`QuoteComputation` (spec.md: "= ScenarioInputs fields" /
"= QuoteComputation fields") -- subclassing keeps them byte-for-byte in sync
with the engine's contract instead of hand-copying every field.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.features.pricing.engine.quote_engine import down_payment_pct_from_amount
from app.features.pricing.engine.types import QuoteComputation, ScenarioInputs, StrategyType


def _to_decimal(value: object) -> Decimal | None:
    """`None` (never raises) for anything that isn't a valid decimal
    number -- lets a `model_validator(mode="before")` degrade to a normal
    Pydantic field-validation 422 on the offending field instead of a bare
    `InvalidOperation`/`TypeError` 500."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


class QuotePreviewRequest(ScenarioInputs):
    """CQ-017: the pricing panel's linked down-payment %/$ input needs to
    send *either* side and have the engine resolve the other, server-side
    (AGENTS.md: money math lives only in `quote_engine`). `down_payment_pct`
    is redeclared optional here (`ScenarioInputs` requires it); a `before`
    validator resolves `down_payment_amount` -> `down_payment_pct` before
    `ScenarioInputs`'s own field/strategy validation ever runs, so every
    downstream consumer of this model still sees a plain, always-populated
    `down_payment_pct` exactly like before.
    """

    down_payment_pct: Decimal | None = None  # type: ignore[assignment]
    down_payment_amount: Decimal | None = None

    @model_validator(mode="before")
    @classmethod
    def _resolve_down_payment(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        pct = data.get("down_payment_pct")
        amount = data.get("down_payment_amount")
        if (pct is None) == (amount is None):
            raise ValueError("Exactly one of down_payment_pct or down_payment_amount is required.")
        if pct is None:
            # Both missing/invalid here fall through to plain `ValueError`s,
            # which Pydantic turns into a normal 422 pointing at the actual
            # offending field(s) -- never a bare `KeyError`/`InvalidOperation`
            # 500 (review finding).
            purchase_price = _to_decimal(data.get("purchase_price"))
            if purchase_price is None:
                raise ValueError("purchase_price must be a valid decimal number.")
            down_payment_amount = _to_decimal(amount)
            if down_payment_amount is None:
                raise ValueError("down_payment_amount must be a valid decimal number.")
            resolved = data.copy()
            resolved["down_payment_pct"] = down_payment_pct_from_amount(
                purchase_price, down_payment_amount
            )
            return resolved
        return data


class QuotePreviewResponse(QuoteComputation):
    """`QuoteComputation` now carries `down_payment_pct` itself (the value
    `compute_quote` actually used) -- this subclass no longer needs to add
    it separately; kept only so the two request/response types stay
    visually paired in this file, matching the module docstring's "= X
    fields" convention."""


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
