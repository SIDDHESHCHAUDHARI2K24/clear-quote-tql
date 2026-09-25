"""`MockCrmClient`: writes to `crm_events`. Never reads -- there is no
"not found" failure mode, only the shared forced-failure path."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.crm.models import CrmEvent
from app.integrations.crm.schemas import CrmEventDTO

ADAPTER = "crm"


class MockCrmClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log_event(
        self, contact_id: str, event_type: str, payload: dict[str, Any]
    ) -> CrmEventDTO:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {"contact_id": contact_id, "event_type": event_type, "payload": payload}

        if await is_forced_to_fail(ADAPTER):
            await record_call(
                self._session,
                ADAPTER,
                request_summary,
                success=False,
                latency_ms=latency_ms,
                error_code="PROVIDER_UNAVAILABLE",
            )
            raise ProviderUnavailableError(ADAPTER)

        at = datetime.now(UTC)
        self._session.add(
            CrmEvent(contact_id=contact_id, event_type=event_type, payload=payload, at=at)
        )

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return CrmEventDTO(contact_id=contact_id, event_type=event_type, at=at)
