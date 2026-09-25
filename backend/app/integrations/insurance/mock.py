"""`MockInsuranceClient`: reads `provider_insurance_factors`.

Never raises a "not found" error -- falls back to the catalog's 0.50%
default factor if `state` has no seeded row, per spec.md.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.insurance.models import ProviderInsuranceFactor
from app.integrations.insurance.schemas import InsuranceEstimateDTO

ADAPTER = "insurance"

_DEFAULT_ANNUAL_RATE_PCT = Decimal("0.50")
_DEFAULT_SOURCE_NAME = "Steadily"


class MockInsuranceClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_insurance_estimate(
        self, state: str, purchase_price: Decimal
    ) -> InsuranceEstimateDTO:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {"state": state, "purchase_price": str(purchase_price)}

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
                select(ProviderInsuranceFactor).where(ProviderInsuranceFactor.state == state)
            )
        ).scalar_one_or_none()

        annual_rate_pct = record.annual_rate_pct if record else _DEFAULT_ANNUAL_RATE_PCT
        source_name = record.source_name if record else _DEFAULT_SOURCE_NAME
        annual_premium = (purchase_price * annual_rate_pct / Decimal("100")).quantize(
            Decimal("0.01")
        )

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return InsuranceEstimateDTO(
            annual_premium=annual_premium,
            annual_rate_pct=annual_rate_pct,
            source_name=source_name,
        )
