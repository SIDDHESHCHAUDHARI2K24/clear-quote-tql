"""`MockRentClient`: reads `provider_rents` (seeded mock RentCast comps)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError, RentDataNotFoundError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.rent.models import ProviderRent
from app.integrations.rent.schemas import MarketRentDTO

ADAPTER = "rent"


class MockRentClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_market_rent(self, zip_code: str, beds: int) -> MarketRentDTO:
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
                select(ProviderRent).where(ProviderRent.zip == zip_code, ProviderRent.beds == beds)
            )
        ).scalar_one_or_none()

        if record is None:
            await record_call(
                self._session,
                ADAPTER,
                request_summary,
                success=False,
                latency_ms=latency_ms,
                error_code="RENT_DATA_NOT_FOUND",
            )
            raise RentDataNotFoundError(zip_code)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return MarketRentDTO(
            market_rent=record.market_rent,
            rent_low=record.rent_low,
            rent_high=record.rent_high,
            comps_count=record.comps_count,
            as_of=record.as_of,
        )
