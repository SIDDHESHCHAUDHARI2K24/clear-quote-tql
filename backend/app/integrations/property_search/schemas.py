"""Property-search request/response DTOs (mock listings search)."""

from __future__ import annotations

import enum
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.integrations.property_search.models import DealGrade


class MatchStrategy(enum.StrEnum):
    """Property search is investment-only, so only LTR/STR apply here
    (unlike `app.features.pricing.engine.types.StrategyType`, which also
    has `PRIMARY` -- kept as a separate, narrower type rather than reusing
    the engine's enum, so `integrations` doesn't couple to `pricing.engine`
    for a field the engine itself never sees)."""

    LTR = "LTR"
    STR = "STR"


class PropertySearchRequestDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved_purchase_price: Decimal
    buy_box_states: list[str]
    buy_box_metros: list[str]
    strategy: MatchStrategy


class PropertyMatchDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    matched_property_id: str
    address: str
    city: str
    state: str
    zip: str
    bed_bath_sqft: str
    deal_grade: DealGrade
    deal_ranking_score: Decimal
    tagline: str | None
    image_url: str
