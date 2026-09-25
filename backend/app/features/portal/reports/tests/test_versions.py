"""`freeze_package_version`: every dollar figure it freezes traces to the
real `quote_engine` (via `auto_price`), never hand-typed here -- matches
`quotes/builder/tests/test_draft_quote_set.py`'s own convention.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.features.applications.models import Application
from app.features.portal.reports.versions import REPORT_EXPIRY_DAYS, freeze_package_version
from app.features.pricing.scenarios.service import auto_price
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion

from .conftest import seed_conventional_rate_sheet, seed_dscr_rate_sheet


def _snapshot(version: QuotePackageVersion) -> dict[str, Any]:
    assert isinstance(version.snapshot, dict)
    return version.snapshot


async def _make_package(
    db_session: AsyncSession, application: Application, quote_ids: list[uuid.UUID]
) -> QuotePackage:
    package = QuotePackage(
        application_id=application.id,
        quote_ids=quote_ids,
        recommended_quote_id=quote_ids[0],
        report_token=secrets.token_urlsafe(24),
    )
    db_session.add(package)
    await db_session.flush()
    return package


async def _priced_primary_application(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> Application:
    application = await make_application(
        occupancy=Occupancy.PRIMARY,
        requested_price=Decimal("300000.00"),
        first_name="Priya",
        last_name="Nair",
    )
    await set_field_value(application.id, "representative_fico", Decimal("760"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.0085"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    seed_conventional_rate_sheet(db_session)
    await db_session.commit()
    return application


async def test_freeze_package_version_snapshot_matches_the_engine(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _priced_primary_application(db_session, make_application, set_field_value)
    pricing_result = await auto_price(db_session, application.id)
    assert pricing_result.quote_ids

    package = await _make_package(db_session, application, list(pricing_result.quote_ids))
    await db_session.commit()

    version = await freeze_package_version(db_session, package=package)
    await db_session.commit()

    assert version.version == 1
    assert version.superseded is False
    assert version.viewed_at is None
    assert version.expires_at - version.sent_at == timedelta(days=REPORT_EXPIRY_DAYS)

    snapshot = _snapshot(version)
    assert snapshot["header"]["first_name"] == "Priya"
    assert snapshot["strategy"] == "primary"
    assert len(snapshot["options"]) == len(pricing_result.quote_ids)
    recommended = [o for o in snapshot["options"] if o["recommended"]]
    assert len(recommended) == 1
    assert recommended[0]["quote_id"] == str(package.recommended_quote_id)
    # Primary never carries investment-only numbers (system-design.md).
    for option in snapshot["options"]:
        assert option["cashflow"] is None
        assert option["cost_seg"] is None
        assert option["hero"]["loan_amount"] is not None
        assert option["hero"]["monthly_cashflow"] is None


async def test_freeze_package_version_investment_ltr_carries_cashflow(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """Investment (LTR): matches
    `pricing/scenarios/tests/test_default_scenarios_investment.py`'s own
    fixture shape, which is proven to price end to end -- this test's job is
    only to prove the DB-row-mapping path itself (Quote/Scenario ->
    ReportOptionInput), not to re-derive STR-specific pricing setup that
    `quotes/report/tests/test_builder.py` (CQ-021) already covers from raw
    `ReportInputs`."""
    application = await make_application(
        occupancy=Occupancy.INVESTMENT,
        strategy=Strategy.LTR,
        requested_price=Decimal("342000.00"),
        first_name="Kathleen",
        last_name="McReynolds",
    )
    await set_field_value(application.id, "representative_fico", Decimal("740"))
    await set_field_value(application.id, "property_tax_annual_rate", Decimal("0.01"))
    await set_field_value(application.id, "homeowners_ins_annual", Decimal("1500.00"))
    await set_field_value(application.id, "market_rent_ltr", Decimal("2440.00"))
    seed_dscr_rate_sheet(db_session, "ONE_TO_1_25", Decimal("7.500"))
    await db_session.commit()

    pricing_result = await auto_price(db_session, application.id)
    assert pricing_result.quote_ids

    package = await _make_package(db_session, application, list(pricing_result.quote_ids))
    await db_session.commit()

    version = await freeze_package_version(db_session, package=package)
    await db_session.commit()

    snapshot = _snapshot(version)
    assert snapshot["strategy"] == "ltr"
    for option in snapshot["options"]:
        assert option["cashflow"] is not None
        assert option["cashflow"]["rent_label"] == "Market rent (LTR)"
        assert option["hero"]["loan_amount"] is None
        assert option["hero"]["monthly_cashflow"] is not None


async def test_freeze_package_version_supersedes_the_prior_version(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _priced_primary_application(db_session, make_application, set_field_value)
    pricing_result = await auto_price(db_session, application.id)
    package = await _make_package(db_session, application, list(pricing_result.quote_ids))
    await db_session.commit()

    first = await freeze_package_version(db_session, package=package)
    await db_session.commit()

    second = await freeze_package_version(db_session, package=package)
    await db_session.commit()

    await db_session.refresh(first)
    assert first.version == 1
    assert first.superseded is True
    assert second.version == 2
    assert second.superseded is False
    assert first.report_token != second.report_token


async def test_freeze_package_version_expired_token_is_computed_not_stored(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await _priced_primary_application(db_session, make_application, set_field_value)
    pricing_result = await auto_price(db_session, application.id)
    package = await _make_package(db_session, application, list(pricing_result.quote_ids))
    await db_session.commit()

    sent_25_days_ago = datetime.now(UTC) - timedelta(days=25)
    version = await freeze_package_version(db_session, package=package, sent_at=sent_25_days_ago)
    await db_session.commit()

    # The frozen snapshot's own `header.expired` is always `false` (frozen
    # at send time) -- the router recomputes it at request time from
    # `expires_at`, never stored `true` here.
    assert _snapshot(version)["header"]["expired"] is False
    assert datetime.now(UTC) > version.expires_at
