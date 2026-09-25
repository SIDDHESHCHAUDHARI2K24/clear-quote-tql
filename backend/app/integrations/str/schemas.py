"""`StrRevenueDTO`: the mock AirDNA short-term-rental response shape."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StrRevenueDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    annual_revenue: Decimal
    occupancy_pct: Decimal
    adr: Decimal
    comps_count: int
    as_of: date
