"""spec.md AC1 (timeline order/messages/quieting), pagination, and E16
scoping (404, not the spec's literal 403 -- plan.md decision 2)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from conftest import StaffSession


async def test_activity_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application()
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/activity")

    assert response.status_code == 401


async def test_activity_404_out_of_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC3-equivalent scoping for the timeline: an LO out of scope gets 404
    (plan.md E16), not the 403 a naive reading of "cannot access" implies."""
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO
    response = await client.get(f"/api/v1/applications/{application.id}/activity")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_activity_order_marcus_hale(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC1: Marcus Hale's real seeded timeline (import -> verify -> price,
    persona p01 is seeded `priced`, not `sent` -- plan.md decision 6) comes
    back newest-first, each row has a non-empty readable message, and every
    row is a genuine system/pipeline event (quiet)."""
    user_result = await seed_users(db_session)
    await seed_providers(db_session)
    personas = {p["key"]: p for p in load_persona_fixtures()}
    marcus = personas["marcus_hale"]

    seed_result = await seed_persona(
        db_session, marcus, lo_id=user_result.lo_ids[0], s3_client=None
    )
    await db_session.commit()

    owner = await make_staff_session(role=UserRole.LO, email="marcus-owner@clearquote-demo.test")
    application = await db_session.get(Application, seed_result.application_id)
    assert application is not None
    application.lo_id = owner.user.id
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/activity")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(seed_result.activity_event_types)
    items = body["items"]
    assert len(items) == len(seed_result.activity_event_types)

    # Newest-first ordering: each row's `at` is >= the next row's `at`.
    timestamps = [datetime.fromisoformat(item["at"]) for item in items]
    assert timestamps == sorted(timestamps, reverse=True)

    # The seed writes imported -> verified -> priced in that order (same
    # types, same count) -- looking each type's position up tolerates a
    # same-instant tie between two `at` values better than a strict
    # index-for-index comparison would.
    by_type = {item["type"]: index for index, item in enumerate(items)}
    assert set(by_type) == set(seed_result.activity_event_types)
    ordered_indexes = [by_type[t] for t in seed_result.activity_event_types]
    assert ordered_indexes == sorted(ordered_indexes, reverse=True)

    for item in items:
        assert item["message"], f"{item['type']} has no message"
        assert item["actor"]["kind"] == "system"
        assert item["actor"]["name"] == "System"


async def test_activity_renders_send_view_borrower_action_and_staff_types(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_activity_event: Callable[..., Awaitable[ActivityEvent]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    """AC1's remaining type categories (send, view, borrower action, a
    staff-actor event) -- Marcus Hale's real state never reaches them
    (plan.md decision 6), so this builds them as fixtures."""
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    now = datetime.now(UTC)
    await make_activity_event(
        application, "quote.sent", payload={"sent_at": now.isoformat()}, at=now - timedelta(days=2)
    )
    await make_activity_event(
        application,
        "quote.viewed",
        payload={"viewed_at": now.isoformat()},
        at=now - timedelta(days=1),
    )
    await make_activity_event(
        application,
        "quote.move_forward",
        payload={"quote_id": "abc", "message": None},
        at=now - timedelta(hours=1),
    )
    await make_activity_event(
        application,
        "application.withdrawn",
        actor=str(owner.user.id),
        payload={"reason": "Found another lender"},
        at=now,
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/activity")
    assert response.status_code == 200
    items = {item["type"]: item for item in response.json()["items"]}

    assert items["quote.sent"]["actor"]["kind"] == "system"
    assert "sent" in items["quote.sent"]["message"].lower()

    assert items["quote.viewed"]["actor"]["kind"] == "borrower"
    assert items["quote.viewed"]["actor"]["name"] == "Test Client"

    assert items["quote.move_forward"]["actor"]["kind"] == "borrower"
    assert "move forward" in items["quote.move_forward"]["message"].lower()

    assert items["application.withdrawn"]["actor"]["kind"] == "staff"
    assert items["application.withdrawn"]["actor"]["name"] == owner.user.full_name
    assert "Found another lender" in items["application.withdrawn"]["message"]


async def test_activity_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_activity_event: Callable[..., Awaitable[ActivityEvent]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    now = datetime.now(UTC)
    for i in range(30):
        await make_activity_event(
            application, "pipeline.imported", payload={}, at=now - timedelta(minutes=i)
        )
    await db_session.commit()

    page1 = (
        await client.get(f"/api/v1/applications/{application.id}/activity", params={"page": 1})
    ).json()
    assert page1["total"] == 30
    assert page1["page_size"] == 25
    assert len(page1["items"]) == 25

    page2 = (
        await client.get(f"/api/v1/applications/{application.id}/activity", params={"page": 2})
    ).json()
    assert len(page2["items"]) == 5
