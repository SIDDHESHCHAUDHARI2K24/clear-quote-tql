"""AC2: `MockRentClient` conforms to `RentClient` and reads `provider_rents`."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import RentDataNotFoundError
from app.integrations.rent.mock import MockRentClient
from app.integrations.rent.models import ProviderRent
from app.integrations.rent.protocol import RentClient
from app.integrations.rent.schemas import MarketRentDTO


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockRentClient(db_session), RentClient)


async def test_get_market_rent_returns_seeded_comp(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderRent(
            zip="28803",
            beds=3,
            market_rent=Decimal("2200.00"),
            rent_low=Decimal("2000.00"),
            rent_high=Decimal("2400.00"),
            comps_count=12,
            as_of=date(2026, 1, 1),
        )
    )
    await db_session.commit()

    result = await MockRentClient(db_session).get_market_rent("28803", 3)

    assert isinstance(result, MarketRentDTO)
    assert result.market_rent == Decimal("2200.00")
    assert result.comps_count == 12


async def test_get_market_rent_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(RentDataNotFoundError) as exc_info:
        await MockRentClient(db_session).get_market_rent("00000", 5)

    assert exc_info.value.zip_code == "00000"
    assert exc_info.value.code == "RENT_DATA_NOT_FOUND"
