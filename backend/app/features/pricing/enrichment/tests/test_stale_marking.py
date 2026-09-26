"""CQ-017 spec.md AC3: overriding or reverting a pricing-affecting
`field_values` row marks every one of that application's quotes stale and
writes an activity event; a non-pricing-affecting field key would not (there
happens to be none today -- every overridable key is pricing-affecting, see
plan.md Decision 8 -- so this file only proves the positive case, matching
what spec.md's AC3 actually exercises).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.pricing.engine.types import ScenarioInputs, StrategyType
from app.features.pricing.enrichment import service as enrichment_service
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.stale import service as stale_service
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


async def _make_priced_scenario(db_session: AsyncSession, application: Application) -> Scenario:
    inputs = ScenarioInputs(
        purchase_price=Decimal("300000.00"),
        down_payment_pct=Decimal("0.20"),
        note_rate=Decimal("0.07"),
        strategy=StrategyType.PRIMARY,
        fico=740,
        property_tax_annual_rate=Decimal("0.006010"),
        insurance_annual_rate=Decimal("0.005"),
    )
    import json

    scenario = Scenario(
        application_id=application.id,
        inputs=json.loads(inputs.model_dump_json()),
        config_snapshot={},
    )
    db_session.add(scenario)
    await db_session.flush()
    quote = Quote(
        scenario_id=scenario.id,
        investor="Mock Investor",
        product="30yr Fixed",
        rate=Decimal("7.000"),
        points=Decimal("0.000"),
        lock_days=30,
        computed={},
        label="Par",
        priced_at=datetime.now(UTC),
    )
    db_session.add(quote)
    await db_session.flush()
    await db_session.commit()
    return scenario


async def test_override_marks_quotes_stale_and_writes_activity_event(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await _seed_tax(db_session)
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    scenario = await _make_priced_scenario(db_session, application)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate",
        json={"value": "0.0250"},
    )
    assert response.status_code == 200

    quotes = (
        (await db_session.execute(select(Quote).where(Quote.scenario_id == scenario.id)))
        .scalars()
        .all()
    )
    assert len(quotes) == 1
    assert quotes[0].stale is True

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "quotes.marked_stale",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, dict)
    assert payload["field_key"] == "property_tax_annual_rate"
    assert payload["action"] == "override"
    # No `field_values` row existed yet for this field before the PATCH
    # (`_make_priced_scenario` seeds a `Scenario`/`Quote` directly, not
    # enrichment output) -- this is a brand-new override, so `old_value`
    # is `None`.
    assert payload["old_value"] is None
    assert payload["new_value"] == "0.0250"
    assert payload["quote_ids"] == [str(quotes[0].id)]


async def test_revert_also_marks_quotes_stale(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await _seed_tax(db_session)
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    scenario = await _make_priced_scenario(db_session, application)
    await db_session.commit()

    patch_response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate",
        json={"value": "0.0250"},
    )
    assert patch_response.status_code == 200

    # Clear the stale flag the PATCH above already set, so the revert's own
    # stale-marking is what this test actually proves.
    quote = (
        await db_session.execute(select(Quote).where(Quote.scenario_id == scenario.id))
    ).scalar_one()
    quote.stale = False
    await db_session.commit()

    revert_response = await client.post(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate/revert"
    )
    assert revert_response.status_code == 200

    await db_session.refresh(quote)
    assert quote.stale is True

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "quotes.marked_stale",
                    ActivityEvent.payload["action"].astext == "revert",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1


async def test_override_with_no_quotes_yet_still_logs_the_change_with_no_quote_ids(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """No scenario/quote exists yet -- nothing to mark stale, but the
    pricing-affecting change is still logged (review finding: the audit
    trail must show every override/revert, not just the ones that hit an
    existing quote); only `quote_ids` is empty, and the override itself
    still succeeds."""
    await _seed_tax(db_session)
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate",
        json={"value": "0.0250"},
    )
    assert response.status_code == 200

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "quotes.marked_stale",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, dict)
    assert payload["quote_ids"] == []
    assert payload["new_value"] == "0.0250"
    # U3 code review: nothing was flagged, so the timeline does not say so.
    assert payload["message"] == "Property tax annual rate overridden"


async def test_override_uses_the_shared_stale_path_with_one_messaged_event(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """U3 (merge plan M4): the override flags quotes through CQ-030's
    `mark_application_quotes_stale` (the one stale path) and the call site
    writes exactly one `quotes.marked_stale` event with a human-readable
    `message` (the CQ-029 timeline shows `payload.message`)."""
    await _seed_tax(db_session)
    staff = await make_staff_session()
    application = await make_application(occupancy=Occupancy.PRIMARY, lo=staff.user)
    scenario = await _make_priced_scenario(db_session, application)
    calls: list[uuid.UUID] = []

    async def _spy(db: AsyncSession, application_id: uuid.UUID, *a: Any, **kw: Any) -> Any:
        calls.append(application_id)
        return await stale_service.mark_application_quotes_stale(db, application_id, *a, **kw)

    monkeypatch.setattr(enrichment_service, "mark_application_quotes_stale", _spy)

    response = await client.patch(
        f"/api/v1/applications/{application.id}/field-values/property_tax_annual_rate",
        json={"value": "0.0250"},
    )
    assert response.status_code == 200, response.text

    assert calls == [application.id]
    quote = (
        await db_session.execute(select(Quote).where(Quote.scenario_id == scenario.id))
    ).scalar_one()
    await db_session.refresh(quote)
    assert quote.stale is True
    [event] = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "quotes.marked_stale",
                )
            )
        )
        .scalars()
        .all()
    )
    assert isinstance(event.payload, dict)
    assert event.payload["message"] == "Quotes marked stale: property tax annual rate overridden"
    assert event.payload["quote_ids"] == [str(quote.id)]
