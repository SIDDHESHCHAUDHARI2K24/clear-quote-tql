"""AC2: `MockCrmClient` conforms to `CrmClient` and writes `crm_events`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.crm.mock import MockCrmClient
from app.integrations.crm.models import CrmEvent
from app.integrations.crm.protocol import CrmClient
from app.integrations.crm.schemas import CrmEventDTO


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockCrmClient(db_session), CrmClient)


async def test_log_event_writes_crm_events_row(db_session: AsyncSession) -> None:
    result = await MockCrmClient(db_session).log_event(
        "contact-123", "quote_sent", {"quote_id": "q-1"}
    )

    assert isinstance(result, CrmEventDTO)
    assert result.contact_id == "contact-123"
    assert result.event_type == "quote_sent"

    rows = (
        (await db_session.execute(select(CrmEvent).where(CrmEvent.contact_id == "contact-123")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].event_type == "quote_sent"
    assert rows[0].payload == {"quote_id": "q-1"}
