"""`MockStrClient`: reads `provider_str_revenue` (seeded mock AirDNA comps)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError, StrDataNotFoundError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.str.models import ProviderStrRevenue
from app.integrations.str.schemas import StrRevenueDTO

ADAPTER = "str"


class MockStrClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_str_revenue(self, zip_code: str, beds: int) -> StrRevenueDTO:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {"zip_code": zip_code, "beds": beds}

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
                select(ProviderStrRevenue).where(
                    ProviderStrRevenue.zip == zip_code, ProviderStrRevenue.beds == beds
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
                error_code="STR_DATA_NOT_FOUND",
            )
            raise StrDataNotFoundError(zip_code)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return StrRevenueDTO(
            annual_revenue=record.annual_revenue,
            occupancy_pct=record.occupancy_pct,
            adr=record.adr,
            comps_count=record.comps_count,
            as_of=record.as_of,
        )
