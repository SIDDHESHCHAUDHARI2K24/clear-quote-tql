"""`TaxClient` Protocol (mock SmartAsset/county)."""

from typing import Protocol, runtime_checkable

from app.integrations.tax.schemas import TaxRateDTO


@runtime_checkable
class TaxClient(Protocol):
    async def get_tax_rate(self, state: str, county: str) -> TaxRateDTO: ...
