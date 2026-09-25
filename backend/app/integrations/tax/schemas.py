"""`TaxRateDTO`: the mock SmartAsset/county tax response shape."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TaxRateDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    annual_rate_pct: Decimal
    source_name: str
    as_of: date
