"""`MockTaxClient`: reads `provider_tax_rates` (seeded mock county rates)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError, TaxRateNotFoundError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.tax.models import ProviderTaxRate
from app.integrations.tax.schemas import TaxRateDTO

ADAPTER = "tax"


class MockTaxClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tax_rate(self, state: str, county: str) -> TaxRateDTO:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {"state": state, "county": county}

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
                select(ProviderTaxRate).where(
                    ProviderTaxRate.state == state, ProviderTaxRate.county == county
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
                error_code="TAX_RATE_NOT_FOUND",
            )
            raise TaxRateNotFoundError(state, county)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return TaxRateDTO(
            annual_rate_pct=record.annual_rate_pct,
            source_name=record.source_name,
            as_of=record.as_of,
        )
