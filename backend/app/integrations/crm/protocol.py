"""`CrmClient` Protocol (mock CRM)."""

from typing import Any, Protocol, runtime_checkable

from app.integrations.crm.schemas import CrmEventDTO


@runtime_checkable
class CrmClient(Protocol):
    async def log_event(
        self, contact_id: str, event_type: str, payload: dict[str, Any]
    ) -> CrmEventDTO: ...
