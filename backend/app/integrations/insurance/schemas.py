"""`InsuranceEstimateDTO`: the mock Steadily response shape."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class InsuranceEstimateDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    annual_premium: Decimal
    annual_rate_pct: Decimal
    source_name: str
