"""AC2: `MockInsuranceClient` conforms to `InsuranceClient`; never raises
"not found" -- falls back to the 0.50% default factor."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.insurance.mock import MockInsuranceClient
from app.integrations.insurance.models import ProviderInsuranceFactor
from app.integrations.insurance.protocol import InsuranceClient
from app.integrations.insurance.schemas import InsuranceEstimateDTO


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockInsuranceClient(db_session), InsuranceClient)


async def test_get_insurance_estimate_uses_seeded_state_factor(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderInsuranceFactor(
            state="FL", annual_rate_pct=Decimal("0.9000"), source_name="Steadily"
        )
    )
    await db_session.commit()

    result = await MockInsuranceClient(db_session).get_insurance_estimate(
        "FL", Decimal("300000.00")
    )

    assert isinstance(result, InsuranceEstimateDTO)
    assert result.annual_rate_pct == Decimal("0.9000")
    assert result.annual_premium == Decimal("2700.00")


async def test_get_insurance_estimate_falls_back_to_default(db_session: AsyncSession) -> None:
    result = await MockInsuranceClient(db_session).get_insurance_estimate(
        "ZZ", Decimal("300000.00")
    )

    assert result.annual_rate_pct == Decimal("0.50")
    assert result.source_name == "Steadily"
    assert result.annual_premium == Decimal("1500.00")
