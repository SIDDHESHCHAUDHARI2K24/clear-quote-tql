"""AC5: every mock call (success or failure) writes exactly one
`integration_calls` row with a correct `latency_ms` and `success` flag."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import LoanNotFoundError
from app.integrations.common.models import IntegrationCall
from app.integrations.los.mock import MockLosClient
from app.integrations.los.models import ProviderLosRecord


async def _los_call_rows(session: AsyncSession) -> list[IntegrationCall]:
    return list(
        (await session.execute(select(IntegrationCall).where(IntegrationCall.adapter == "los")))
        .scalars()
        .all()
    )


async def test_success_writes_one_row_with_latency_and_success(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderLosRecord(loan_number="LN-LOG-1", payload={"occupancy_type": "Primary_Residence"})
    )
    await db_session.commit()

    await MockLosClient(db_session).get_loan_file("LN-LOG-1")

    rows = await _los_call_rows(db_session)
    assert len(rows) == 1
    assert rows[0].success is True
    assert rows[0].error_code is None
    assert rows[0].latency_ms == 0  # latency disabled for the whole test session
    assert rows[0].request_summary == {"loan_number": "LN-LOG-1"}


async def test_failure_writes_one_row_with_error_code(db_session: AsyncSession) -> None:
    with pytest.raises(LoanNotFoundError):
        await MockLosClient(db_session).get_loan_file("MISSING-LOAN")

    rows = await _los_call_rows(db_session)
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].error_code == "LOAN_NOT_FOUND"
    assert rows[0].latency_ms == 0
