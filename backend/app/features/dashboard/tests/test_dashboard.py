"""`GET /api/v1/dashboard` (CQ-025 spec.md)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, ApplicationTab, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.verification.models import Flag
from app.features.auth.sessions.service import COOKIE_NAMES
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion


async def test_dashboard_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 401


async def test_dashboard_tiles_match_sql(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
    make_property: Callable[..., Awaitable[Property]],
    make_sent_version: Callable[..., Awaitable],
) -> None:
    """AC1: every tile count for a Manager equals a direct SQL count of the
    spec.md definition (computed independently of `dashboard.service`).

    "Pre-approvals sent" is "Stale after a send" (spec.md) -- a Stale
    application only counts when a `quote_package_versions` row actually
    exists for it (it was sent, then aged out); a Stale application that
    aged out straight from Priced without ever being sent (CQ-030 spec.md)
    must NOT count. The oracle SQL below encodes that with its own EXISTS
    subquery, independent of `applications.listing.service`'s
    `build_sent_or_later_filter()`."""
    await make_staff_session(role=UserRole.MANAGER)

    statuses = [
        ApplicationStatus.INTAKE,
        ApplicationStatus.NEEDS_ATTENTION,
        ApplicationStatus.PRICED,
        ApplicationStatus.SENT,
        ApplicationStatus.VIEWED,
        ApplicationStatus.INQUIRY,
        ApplicationStatus.OPTION_SELECTED,
        ApplicationStatus.STALE,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.CLOSED,
    ]
    apps = [await make_application(status=status) for status in statuses]
    # One of the priced apps has a specific-address property.
    await make_property(apps[2].id, PropertyAddressStatus.SPECIFIC_ADDRESS)
    await make_property(apps[0].id, PropertyAddressStatus.TBD)

    # apps[7] (STALE) was actually sent before it went stale -- must count.
    await make_sent_version(apps[7].id, sent_at=datetime.now(UTC) - timedelta(days=25))
    # A second STALE application that aged out straight from Priced,
    # never sent -- must NOT count (CQ-030 spec.md).
    stale_never_sent = await make_application(status=ApplicationStatus.STALE)

    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    tiles = response.json()["tiles"]

    not_active = {ApplicationStatus.WITHDRAWN.value, ApplicationStatus.CLOSED.value}
    pre_approval_sent_base = {
        ApplicationStatus.SENT.value,
        ApplicationStatus.VIEWED.value,
        ApplicationStatus.INQUIRY.value,
        ApplicationStatus.OPTION_SELECTED.value,
    }
    awaiting_review = {
        ApplicationStatus.PRICED.value,
        ApplicationStatus.INQUIRY.value,
        ApplicationStatus.OPTION_SELECTED.value,
    }

    sql_clients = (
        await db_session.execute(select(func.count(func.distinct(Application.client_id))))
    ).scalar_one()
    sql_applications = (
        await db_session.execute(select(func.count()).where(Application.status.notin_(not_active)))
    ).scalar_one()
    sent_exists = (
        select(QuotePackageVersion.id)
        .join(QuotePackage, QuotePackageVersion.package_id == QuotePackage.id)
        .where(QuotePackage.application_id == Application.id)
        .correlate(Application)
        .exists()
    )
    sql_pre_approvals_sent = (
        await db_session.execute(
            select(func.count()).where(
                or_(
                    Application.status.in_(pre_approval_sent_base),
                    and_(Application.status == ApplicationStatus.STALE, sent_exists),
                )
            )
        )
    ).scalar_one()
    sql_with_property = (
        await db_session.execute(
            select(func.count())
            .select_from(Application)
            .join(Property, Property.application_id == Application.id)
            .where(Property.address_status == PropertyAddressStatus.SPECIFIC_ADDRESS)
        )
    ).scalar_one()
    sql_awaiting_review = (
        await db_session.execute(
            select(func.count()).where(Application.status.in_(awaiting_review))
        )
    ).scalar_one()
    sql_needs_attention = (
        await db_session.execute(
            select(func.count()).where(Application.status == ApplicationStatus.NEEDS_ATTENTION)
        )
    ).scalar_one()
    sql_stale_quotes = (
        await db_session.execute(
            select(func.count()).where(Application.status == ApplicationStatus.STALE)
        )
    ).scalar_one()

    assert tiles["clients"] == sql_clients
    assert tiles["applications"] == sql_applications
    assert tiles["pre_approvals_sent"] == sql_pre_approvals_sent
    assert tiles["with_property"] == sql_with_property
    assert tiles["awaiting_review"] == sql_awaiting_review
    assert tiles["needs_attention"] == sql_needs_attention
    assert tiles["stale_quotes"] == sql_stale_quotes

    # Sanity: the counts are not all trivially zero, and the Stale-but-
    # never-sent application is excluded from "pre-approvals sent" while
    # still counting in "applications" and "stale quotes".
    assert tiles["applications"] == len(apps) - 2 + 1  # +1 for stale_never_sent
    assert tiles["with_property"] == 1
    assert tiles["stale_quotes"] == 2  # apps[7] (sent) and stale_never_sent
    assert tiles["pre_approvals_sent"] == 5  # SENT/VIEWED/INQUIRY/OPTION_SELECTED + apps[7]
    assert stale_never_sent.status == ApplicationStatus.STALE


async def test_sent_or_later_matches_dashboard(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
    make_sent_version: Callable[..., Awaitable],
) -> None:
    """AC3/E10 cross-check: the dashboard's "Pre-approvals sent" tile count
    equals `GET /api/v1/applications?status=sent_or_later`'s `total` --
    both for a Manager (all files) and for one LO (their own files). Both
    endpoints share `applications.listing.service.build_sent_or_later_filter()`
    (plan.md Decision #6/E10), so this also exercises the fix that removed
    the dashboard's own locally-duplicated status set."""
    lo_session = await make_staff_session(role=UserRole.LO)
    lo_user = lo_session.user
    other_lo_session = await make_staff_session(role=UserRole.LO)
    other_lo_user = other_lo_session.user

    # This LO: one of each "sent or later" status, a Stale that was sent
    # (counts) and a Stale that never was (must not count), plus a Priced
    # application (must not count).
    await make_application(lo=lo_user, status=ApplicationStatus.SENT)
    await make_application(lo=lo_user, status=ApplicationStatus.VIEWED)
    await make_application(lo=lo_user, status=ApplicationStatus.INQUIRY)
    await make_application(lo=lo_user, status=ApplicationStatus.OPTION_SELECTED)
    stale_sent = await make_application(lo=lo_user, status=ApplicationStatus.STALE)
    await make_sent_version(stale_sent.id, sent_at=datetime.now(UTC) - timedelta(days=25))
    await make_application(lo=lo_user, status=ApplicationStatus.STALE)  # never sent
    await make_application(lo=lo_user, status=ApplicationStatus.PRICED)

    # Another LO's sent application must not leak into the first LO's
    # count, but must show up once a Manager looks at everything.
    await make_application(lo=other_lo_user, status=ApplicationStatus.SENT)

    client.cookies.set(COOKIE_NAMES["staff"], lo_session.token)
    lo_dashboard = await client.get("/api/v1/dashboard")
    assert lo_dashboard.status_code == 200
    lo_tile = lo_dashboard.json()["tiles"]["pre_approvals_sent"]

    lo_list = await client.get("/api/v1/applications", params={"status": "sent_or_later"})
    assert lo_list.status_code == 200
    lo_total = lo_list.json()["total"]

    assert lo_tile == lo_total == 5  # sent, viewed, inquiry, option_selected, stale_sent

    await make_staff_session(role=UserRole.MANAGER)
    manager_dashboard = await client.get("/api/v1/dashboard")
    manager_tile = manager_dashboard.json()["tiles"]["pre_approvals_sent"]

    manager_list = await client.get("/api/v1/applications", params={"status": "sent_or_later"})
    manager_total = manager_list.json()["total"]

    assert manager_tile == manager_total == 6  # + the other LO's sent application


async def test_dashboard_scoping(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    """AC2: an LO sees only their own files; a Manager filtering by that LO
    sees the same numbers."""
    lo_session = await make_staff_session(role=UserRole.LO)
    lo_user = lo_session.user
    other_lo_session = await make_staff_session(role=UserRole.LO)
    other_lo_user = other_lo_session.user

    await make_application(lo=lo_user, status=ApplicationStatus.PRICED)
    await make_application(lo=lo_user, status=ApplicationStatus.SENT)
    await make_application(lo=other_lo_user, status=ApplicationStatus.PRICED)

    # Sign back in as the first LO -- reuse the token `make_staff_session`
    # already minted for them (calling it again with the same email would
    # try to INSERT a second `users` row with that email and 409 on the
    # unique index).
    client.cookies.set(COOKIE_NAMES["staff"], lo_session.token)
    lo_response = await client.get("/api/v1/dashboard")
    assert lo_response.status_code == 200
    lo_tiles = lo_response.json()["tiles"]
    assert lo_tiles["applications"] == 2
    assert lo_response.json()["los"] is None

    await make_staff_session(role=UserRole.MANAGER)
    manager_response = await client.get("/api/v1/dashboard", params={"lo_id": str(lo_user.id)})
    assert manager_response.status_code == 200
    manager_tiles = manager_response.json()["tiles"]
    assert manager_tiles == lo_tiles
    assert manager_response.json()["los"] is not None

    # A bare `lo_id` on an LO caller is ignored -- they always see their own.
    client.cookies.set(COOKIE_NAMES["staff"], lo_session.token)
    ignored_response = await client.get(
        "/api/v1/dashboard", params={"lo_id": str(other_lo_user.id)}
    )
    assert ignored_response.json()["tiles"] == lo_tiles


async def test_dashboard_lists_personas(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
    make_flag: Callable[..., Awaitable[Flag]],
    make_recommended_quote: Callable[..., Awaitable],
    make_sent_version: Callable[..., Awaitable],
) -> None:
    """AC3: Aisha appears in "Needs your attention" with her missing-field
    reason; Luis appears with his selected option; Grace appears in "Going
    stale" with her age in days."""
    await make_staff_session(role=UserRole.MANAGER)
    now = datetime.now(UTC)

    aisha = await make_application(
        status=ApplicationStatus.NEEDS_ATTENTION,
        client_name="Aisha Coleman",
        updated_at=now - timedelta(days=1),
    )
    await make_flag(
        aisha.id,
        message="Cannot price: missing Occupancy",
        tab=ApplicationTab.BORROWERS,
        rule="ob_required_field",
    )

    luis = await make_application(
        status=ApplicationStatus.OPTION_SELECTED,
        client_name="Luis Romero",
        updated_at=now - timedelta(days=3),
    )
    await make_sent_version(
        luis.id,
        sent_at=now - timedelta(days=3),
        borrower_action={"type": "option_selected", "quote_id": "quote-1"},
        options=[{"quote_id": "quote-1", "label": "30yr Fixed at 7.125%"}],
    )

    grace = await make_application(
        status=ApplicationStatus.SENT,
        client_name="Grace Kim",
        updated_at=now - timedelta(days=25),
    )
    await make_recommended_quote(grace, priced_at=now - timedelta(days=25))
    await make_sent_version(grace.id, sent_at=now - timedelta(days=25))

    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()

    attention_by_name = {row["client_name"]: row for row in body["attention"]}
    assert attention_by_name["Aisha Coleman"]["status"] == "needs_attention"
    assert attention_by_name["Aisha Coleman"]["reason"] == "Cannot price: missing Occupancy"
    assert attention_by_name["Luis Romero"]["status"] == "option_selected"
    assert attention_by_name["Luis Romero"]["reason"] == "30yr Fixed at 7.125%"

    stale_by_name = {row["client_name"]: row for row in body["stale"]}
    assert "Grace Kim" in stale_by_name
    assert stale_by_name["Grace Kim"]["days_old"] >= 21
    assert "Luis Romero" not in stale_by_name


async def test_attention_reason_uses_the_most_recently_sent_version(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
    make_sent_version: Callable[..., Awaitable],
) -> None:
    """Code-review finding (cq-025-fix): `_latest_sent_versions` must pick
    the `QuotePackageVersion` with the most recent `sent_at`, not the one
    with the highest `version` number -- `quote_packages.application_id`
    has no unique constraint, so an application with more than one
    `QuotePackage` row (not possible via today's application code, but not
    prevented by the schema either) must still resolve to the version that
    was actually sent most recently, matching `_build_stale`'s own
    `latest_sent_at` definition. Simulates that with two separate
    `QuotePackage` rows for the same application -- an older one with a
    *higher* version number, and a newer one (by `sent_at`) with a *lower*
    version number -- and asserts the newer one's reason wins."""
    await make_staff_session(role=UserRole.MANAGER)
    now = datetime.now(UTC)

    application = await make_application(
        status=ApplicationStatus.OPTION_SELECTED, client_name="Priya Older Package"
    )
    # Older package, sent 10 days ago, but a higher version number.
    await make_sent_version(
        application.id,
        sent_at=now - timedelta(days=10),
        version=5,
        borrower_action={"type": "option_selected", "quote_id": "stale-quote"},
        options=[{"quote_id": "stale-quote", "label": "Stale label -- must not win"}],
    )
    # Newer package, sent yesterday, with a lower version number.
    await make_sent_version(
        application.id,
        sent_at=now - timedelta(days=1),
        version=1,
        borrower_action={"type": "option_selected", "quote_id": "fresh-quote"},
        options=[{"quote_id": "fresh-quote", "label": "Fresh label -- must win"}],
    )

    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    attention_by_name = {row["client_name"]: row for row in response.json()["attention"]}

    assert attention_by_name["Priya Older Package"]["reason"] == "Fresh label -- must win"


async def test_attention_list_updates_after_resolve(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
    make_flag: Callable[..., Awaitable[Flag]],
) -> None:
    """AC5 (pending -- re-check after CQ-027/CQ-028): resolving the flag
    (and, as CQ-028's real re-verify flow will do, the status moving off
    NeedsAttention) removes the application from the attention list. Done
    directly against the DB here, per the coordinator's E2E note, rather
    than through CQ-028's not-yet-built re-verify endpoint."""
    await make_staff_session(role=UserRole.MANAGER)
    application = await make_application(
        status=ApplicationStatus.NEEDS_ATTENTION, client_name="Ben Flagged"
    )
    flag = await make_flag(application.id, message="Cannot price: missing Occupancy")

    before = await client.get("/api/v1/dashboard")
    assert "Ben Flagged" in {row["client_name"] for row in before.json()["attention"]}

    flag.resolved_at = datetime.now(UTC)
    application.status = ApplicationStatus.READY_TO_PRICE
    await db_session.flush()
    await db_session.commit()

    after = await client.get("/api/v1/dashboard")
    assert "Ben Flagged" not in {row["client_name"] for row in after.json()["attention"]}


async def test_dashboard_latency(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    """AC6: responds fast with ~200 seeded applications. A generous 1s
    ceiling is used here to absorb shared-CI/test-DB overhead; the manual
    e2e recipe (post-dev.md) measures the real number against a
    `make demo-reset` database."""
    await make_staff_session(role=UserRole.MANAGER)
    for _ in range(200):
        await make_application(status=ApplicationStatus.PRICED)

    start = time.monotonic()
    response = await client.get("/api/v1/dashboard")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 1.0, f"dashboard took {elapsed:.3f}s"


async def test_dashboard_activity_orders_newest_first_and_resolves_actor(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable],
    make_application: Callable[..., Awaitable[Application]],
    make_activity_event: Callable[..., Awaitable],
) -> None:
    """`activity`: the latest 20 events across the LO's applications,
    newest first; a user-id actor resolves to that staff member's name, and
    `"system"` resolves to "System"."""
    staff = await make_staff_session(role=UserRole.MANAGER)
    lo_user = staff.user
    application = await make_application(lo=lo_user, client_name="Nina Client")
    now = datetime.now(UTC)

    await make_activity_event(
        application.id, actor="system", type_="pipeline.priced", at=now - timedelta(hours=2)
    )
    await make_activity_event(
        application.id, actor=str(lo_user.id), type_="application.withdrawn", at=now
    )

    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    activity = response.json()["activity"]

    assert [row["type"] for row in activity] == ["application.withdrawn", "pipeline.priced"]
    assert activity[0]["actor"] == lo_user.full_name
    assert activity[1]["actor"] == "System"
    assert all(row["client_name"] == "Nina Client" for row in activity)
