"""AC2: `MockTaxClient` conforms to `TaxClient` and reads `provider_tax_rates`."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import TaxRateNotFoundError
from app.integrations.tax.mock import MockTaxClient
from app.integrations.tax.models import ProviderTaxRate
from app.integrations.tax.protocol import TaxClient
from app.integrations.tax.schemas import TaxRateDTO


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockTaxClient(db_session), TaxClient)


async def test_get_tax_rate_returns_seeded_rate(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderTaxRate(
            county="Buncombe",
            state="NC",
            annual_rate_pct=Decimal("0.6010"),
            source_name="SmartAsset",
            as_of=date(2026, 1, 1),
        )
    )
    await db_session.commit()

    result = await MockTaxClient(db_session).get_tax_rate("NC", "Buncombe")

    assert isinstance(result, TaxRateDTO)
    assert result.annual_rate_pct == Decimal("0.6010")
    assert result.source_name == "SmartAsset"


async def test_get_tax_rate_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(TaxRateNotFoundError) as exc_info:
        await MockTaxClient(db_session).get_tax_rate("ZZ", "Nowhere")

    assert exc_info.value.state == "ZZ"
    assert exc_info.value.county == "Nowhere"
    assert exc_info.value.code == "TAX_RATE_NOT_FOUND"
