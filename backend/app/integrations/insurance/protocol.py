"""`InsuranceClient` Protocol (mock Steadily)."""

from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.integrations.insurance.schemas import InsuranceEstimateDTO


@runtime_checkable
class InsuranceClient(Protocol):
    async def get_insurance_estimate(
        self, state: str, purchase_price: Decimal
    ) -> InsuranceEstimateDTO: ...
