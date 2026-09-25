"""AC2: `MockPricingClient` conforms to `PricingClient`."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.pricing.mock import MockPricingClient
from app.integrations.pricing.protocol import PricingClient


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockPricingClient(db_session), PricingClient)
