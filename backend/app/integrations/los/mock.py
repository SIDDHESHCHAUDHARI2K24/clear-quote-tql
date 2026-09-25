"""`MockLosClient`: reads `provider_los_records` (seeded mock Encompass data)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import LoanNotFoundError, ProviderUnavailableError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.los.models import ProviderLosRecord
from app.integrations.los.schemas import LoanFileDTO

ADAPTER = "los"


class MockLosClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_loan_file(self, loan_number: str) -> LoanFileDTO:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {"loan_number": loan_number}

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

        record = (
            await self._session.execute(
                select(ProviderLosRecord).where(ProviderLosRecord.loan_number == loan_number)
            )
        ).scalar_one_or_none()

        if record is None:
            await record_call(
                self._session,
                ADAPTER,
                request_summary,
                success=False,
                latency_ms=latency_ms,
                error_code="LOAN_NOT_FOUND",
            )
            raise LoanNotFoundError(loan_number)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        payload = record.payload if isinstance(record.payload, dict) else {}
        return LoanFileDTO(loan_number=loan_number, **payload)
