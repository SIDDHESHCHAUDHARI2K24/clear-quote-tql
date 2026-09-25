"""AC2: `MockStrClient` conforms to `StrClient` and reads `provider_str_revenue`."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import StrDataNotFoundError
from app.integrations.str.mock import MockStrClient
from app.integrations.str.models import ProviderStrRevenue
from app.integrations.str.protocol import StrClient
from app.integrations.str.schemas import StrRevenueDTO


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockStrClient(db_session), StrClient)


async def test_get_str_revenue_returns_seeded_comp(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderStrRevenue(
            zip="33896",
            beds=4,
            annual_revenue=Decimal("62000.00"),
            occupancy_pct=Decimal("68.50"),
            adr=Decimal("245.00"),
            comps_count=9,
            as_of=date(2026, 1, 1),
        )
    )
    await db_session.commit()

    result = await MockStrClient(db_session).get_str_revenue("33896", 4)

    assert isinstance(result, StrRevenueDTO)
    assert result.annual_revenue == Decimal("62000.00")
    assert result.comps_count == 9


async def test_get_str_revenue_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(StrDataNotFoundError) as exc_info:
        await MockStrClient(db_session).get_str_revenue("00000", 5)

    assert exc_info.value.zip_code == "00000"
    assert exc_info.value.code == "STR_DATA_NOT_FOUND"
