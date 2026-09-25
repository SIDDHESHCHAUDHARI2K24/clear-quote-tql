"""`MockCreditClient`: reads `provider_credit_reports`.

Soft pull populates `experian_score` only (per catalog: "Soft pull only
pulls Experian") -- that split is baked into the seeded row itself (CQ-010),
not computed here; this mock only returns what's stored.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import CreditPullFailedError, ProviderUnavailableError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.credit.models import CreditPullType, ProviderCreditReport
from app.integrations.credit.schemas import CreditReportDTO

ADAPTER = "credit"


class MockCreditClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pull_credit(self, loan_number: str, pull_type: CreditPullType) -> CreditReportDTO:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {"loan_number": loan_number, "pull_type": pull_type.value}

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
                select(ProviderCreditReport).where(
                    ProviderCreditReport.loan_number == loan_number,
                    ProviderCreditReport.pull_type == pull_type,
                )
            )
        ).scalar_one_or_none()

        if record is None:
            await record_call(
                self._session,
                ADAPTER,
                request_summary,
                success=False,
                latency_ms=latency_ms,
                error_code="CREDIT_PULL_FAILED",
            )
            raise CreditPullFailedError(loan_number, pull_type)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return CreditReportDTO(
            pull_type=record.pull_type,
            experian_score=record.experian_score,
            equifax_score=record.equifax_score,
            transunion_score=record.transunion_score,
            middle_score=record.middle_score,
            tradelines=record.tradelines,
        )
