"""`RentClient` Protocol (mock RentCast)."""

from typing import Protocol, runtime_checkable

from app.integrations.rent.schemas import MarketRentDTO


@runtime_checkable
class RentClient(Protocol):
    async def get_market_rent(self, zip_code: str, beds: int) -> MarketRentDTO: ...
