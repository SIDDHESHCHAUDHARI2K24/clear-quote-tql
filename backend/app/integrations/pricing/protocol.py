"""`PricingClient` Protocol (mock Optimal Blue)."""

from typing import Protocol, runtime_checkable

from app.integrations.pricing.schemas import PricedProductDTO, PricingRequestDTO


@runtime_checkable
class PricingClient(Protocol):
    async def get_priced_products(self, request: PricingRequestDTO) -> list[PricedProductDTO]: ...
