"""AC4: the failure toggle is per-adapter and forces/clears failure."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError, TaxRateNotFoundError
from app.integrations.common.failure_toggle import is_forced_to_fail, set_forced_failure
from app.integrations.rent.mock import MockRentClient
from app.integrations.tax.mock import MockTaxClient


async def test_defaults_to_not_forced() -> None:
    assert await is_forced_to_fail("rent") is False


async def test_set_forced_failure_forces_and_clears() -> None:
    await set_forced_failure("rent", True)
    assert await is_forced_to_fail("rent") is True

    await set_forced_failure("rent", False)
    assert await is_forced_to_fail("rent") is False


async def test_toggle_is_scoped_to_one_adapter(db_session: AsyncSession) -> None:
    await set_forced_failure("rent", True)

    rent_client = MockRentClient(db_session)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await rent_client.get_market_rent("28803", 3)
    assert exc_info.value.adapter == "rent"

    # `tax` is untouched by forcing `rent` -- it still runs its normal
    # lookup and raises its own not-found error (no seeded row), not
    # ProviderUnavailableError.
    tax_client = MockTaxClient(db_session)
    with pytest.raises(TaxRateNotFoundError):
        await tax_client.get_tax_rate("NC", "Buncombe")

    await set_forced_failure("rent", False)
