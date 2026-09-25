"""`MarketRentDTO`: the mock RentCast long-term-rent response shape."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MarketRentDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    market_rent: Decimal
    rent_low: Decimal
    rent_high: Decimal
    comps_count: int
    as_of: date
