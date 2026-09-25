"""`PropertySearchClient` Protocol (mock property search)."""

from typing import Protocol, runtime_checkable

from app.integrations.property_search.schemas import PropertyMatchDTO, PropertySearchRequestDTO


@runtime_checkable
class PropertySearchClient(Protocol):
    async def search_matches(self, request: PropertySearchRequestDTO) -> list[PropertyMatchDTO]: ...
