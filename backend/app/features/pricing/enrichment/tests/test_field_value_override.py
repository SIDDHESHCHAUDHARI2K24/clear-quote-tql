"""AC3: `PATCH .../field-values/{field_key}` sets `overridden_by`/
`overridden_at`; `POST .../revert` restores the pre-override value (by
re-running that field's own enrichment fetch) and clears them.
"""

from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy
from app.features.applications.models import Application
from app.integrations.tax.models import ProviderTaxRate
from conftest import StaffSession


async def _seed_tax(db_session: AsyncSession) -> None:
    db_session.add(
        ProviderTaxRate(
            state="NC",
            county="Buncombe",
            annual_rate_pct=Decimal("0.6010"),
            source_name="SmartAsset",
            as_of=date(2026, 1, 1),
        )
    )
    await db_session.flush()
    await db_session.commit()


async def test_patch_field_value_sets_override(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await _seed_tax(db_session)
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate",
        json={"value": "0.0250"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["field_key"] == "property_tax_annual_rate"
    assert Decimal(body["value"]) == Decimal("0.0250")
    assert body["source"] == "lo_override"
    assert body["overridden_by"] is not None
    assert body["overridden_at"] is not None


async def test_revert_restores_source_value_and_clears_override(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await _seed_tax(db_session)
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    await db_session.commit()

    patch_response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate",
        json={"value": "0.0250"},
    )
    assert patch_response.status_code == 200

    revert_response = await client.post(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate/revert"
    )

    assert revert_response.status_code == 200
    body = revert_response.json()
    assert Decimal(body["value"]) == Decimal("0.6010") / Decimal("100")
    assert body["source"] == "smartasset"
    assert body["overridden_by"] is None
    assert body["overridden_at"] is None


async def test_revert_not_overridable_field_key_is_422(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/applications/{application.id}/field-values/not_a_real_field/revert"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
