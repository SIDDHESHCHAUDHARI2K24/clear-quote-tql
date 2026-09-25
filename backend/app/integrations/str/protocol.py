"""`StrClient` Protocol (mock AirDNA)."""

from typing import Protocol, runtime_checkable

from app.integrations.str.schemas import StrRevenueDTO


@runtime_checkable
class StrClient(Protocol):
    async def get_str_revenue(self, zip_code: str, beds: int) -> StrRevenueDTO: ...
