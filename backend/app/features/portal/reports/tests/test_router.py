"""`GET /api/v1/portal/reports/{token}` (CQ-022 spec.md AC1/AC2/AC4/AC5).

AC1 note (spec.md "Notes for the agent"): this item can run before CQ-020,
so AC1 is verified here with the sent-version factory directly, against a
real engine-priced package (via `auto_price`) -- not a hand-typed snapshot.
The coordinator re-checks AC1 end to end once CQ-020's real send workflow
lands (post-dev.md records both).
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Occupancy
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.clients.models import Client
from app.features.portal.reports.versions import freeze_package_version
from app.features.pricing.scenarios.service import auto_price
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from conftest import BorrowerSession

from .conftest import seed_conventional_rate_sheet

MakeBorrowerSession = Callable[..., Awaitable[BorrowerSession]]


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


async def _version_for_package(
    db_session: AsyncSession, package: QuotePackage
) -> QuotePackageVersion:
    version = (
        (
            await db_session.execute(
                select(QuotePackageVersion)
                .where(QuotePackageVersion.package_id == package.id)
                .order_by(QuotePackageVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    assert version is not None
    return version


async def _priced_package(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
    *,
    sent_at: datetime | None = None,
) -> tuple[Application, QuotePackage]:
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

    pricing_result = await auto_price(db_session, application.id)
    package = await _make_package(db_session, application, list(pricing_result.quote_ids))
    application.status = ApplicationStatus.SENT
    await db_session.commit()

    await freeze_package_version(db_session, package=package, sent_at=sent_at)
    await db_session.commit()
    return application, package


async def test_get_report_returns_frozen_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, package = await _priced_package(db_session, make_application, set_field_value)
    version = await _version_for_package(db_session, package)

    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)

    response = await client.get(f"/api/v1/portal/reports/{version.report_token}")

    assert response.status_code == 200
    body = response.json()
    assert body["header"]["first_name"] == "Priya"
    assert body["header"]["expired"] is False
    assert body["header"]["superseded"] is False
    assert body["borrower_action"] is None
    assert len(body["options"]) == len(package.quote_ids)
    # The response equals the frozen snapshot -- same option quote_ids/rates.
    assert [o["quote_id"] for o in body["options"]] == [
        o["quote_id"] for o in _snapshot(version)["options"]
    ]
    assert [o["rate"] for o in body["options"]] == [
        o["rate"] for o in _snapshot(version)["options"]
    ]


async def test_first_view_sets_viewed_once(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, package = await _priced_package(db_session, make_application, set_field_value)
    version = await _version_for_package(db_session, package)

    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)

    assert version.viewed_at is None

    first = await client.get(f"/api/v1/portal/reports/{version.report_token}")
    assert first.status_code == 200

    await db_session.refresh(version)
    assert version.viewed_at is not None
    await db_session.refresh(application)
    assert application.status is ApplicationStatus.VIEWED

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "quote.viewed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    first_viewed_at = version.viewed_at

    # Reload -- writes no second event, does not change viewed_at.
    second = await client.get(f"/api/v1/portal/reports/{version.report_token}")
    assert second.status_code == 200

    await db_session.refresh(version)
    assert version.viewed_at == first_viewed_at

    events_after = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application.id,
                    ActivityEvent.type == "quote.viewed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events_after) == 1


async def test_expired_flag(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    sent_25_days_ago = datetime.now(UTC) - timedelta(days=25)
    application, package = await _priced_package(
        db_session, make_application, set_field_value, sent_at=sent_25_days_ago
    )
    version = await _version_for_package(db_session, package)

    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)

    response = await client.get(f"/api/v1/portal/reports/{version.report_token}")
    assert response.status_code == 200
    assert response.json()["header"]["expired"] is True
    # No action buttons state is a frontend concern (ReportActionsSlot);
    # the API just carries `expired`, asserted above (spec.md AC4).


async def test_report_token_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    _application, package = await _priced_package(db_session, make_application, set_field_value)
    version = await _version_for_package(db_session, package)

    # A *different* borrower (their own, unrelated client) signs in.
    await make_borrower_session(None)

    response = await client.get(f"/api/v1/portal/reports/{version.report_token}")
    assert response.status_code == 404

    # A random, never-issued token also 404s.
    random_token_response = await client.get("/api/v1/portal/reports/not-a-real-token")
    assert random_token_response.status_code == 404


async def test_superseded_version_carries_the_newest_token(
    client: AsyncClient,
    db_session: AsyncSession,
    make_borrower_session: MakeBorrowerSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application, package = await _priced_package(db_session, make_application, set_field_value)
    old_version = await _version_for_package(db_session, package)

    new_version = await freeze_package_version(db_session, package=package)
    await db_session.commit()

    client_row = await db_session.get(Client, application.client_id)
    await make_borrower_session(client_row)

    response = await client.get(f"/api/v1/portal/reports/{old_version.report_token}")
    assert response.status_code == 200
    body = response.json()
    assert body["header"]["superseded"] is True
    assert body["newest_report_token"] == new_version.report_token
