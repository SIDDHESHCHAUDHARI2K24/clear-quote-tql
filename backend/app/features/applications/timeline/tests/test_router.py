"""spec.md AC1 (timeline order/messages/quieting), pagination, and E16
scoping (404, not the spec's literal 403 -- plan.md decision 2)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
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


_STAFF = "__staff__"

# M2: one entry per event type actually written in the base -- from
# `ActivityEvent(` call sites (workflows/activities.py, portal/*/service.py,
# quotes/stale/service.py, applications/summary/service.py) and the
# `type=events.*` constants in applications/sections/events.py (written by
# fields.py, property.py, reverify.py, credit.py, router.py, collections.py).
# `quote.sent`/`quote.option_selected` have no writer yet (CQ-020 not
# built) -- already covered by
# `test_activity_renders_send_view_borrower_action_and_staff_types` above.
_WRITTEN_EVENTS: list[tuple[str, str, dict[str, object], str]] = [
    ("pipeline.imported", "system", {"parties_created": 2}, "system"),
    ("pipeline.verified", "system", {"rule_count": 5}, "system"),
    ("pipeline.flagged", "system", {"failed_rules": ["dti_max"]}, "system"),
    ("pipeline.enriched", "system", {"field_keys_written": ["a", "b"]}, "system"),
    (
        "pipeline.pricing_blocked",
        "system",
        {"message": "Cannot price: pricing unavailable"},
        "system",
    ),
    ("pipeline.priced", "system", {"quote_ids": ["q1", "q2"]}, "system"),
    ("pipeline.resumed", "system", {}, "system"),
    ("quote.viewed", "system", {"version": 1}, "borrower"),
    ("quote.move_forward", "system", {"quote_id": "abc"}, "borrower"),
    ("quote.ask_other", "system", {"quote_id": "abc"}, "borrower"),
    ("quote.ask_updated", "system", {"quote_id": "abc"}, "borrower"),
    ("application.withdrawn", _STAFF, {"reason": "Found another lender"}, "staff"),
    ("application.closed", _STAFF, {"reason": "Funded elsewhere"}, "staff"),
    ("application.submitted", "borrower", {"source": "portal", "draft_id": "d1"}, "borrower"),
    (
        "application.assigned",
        "system",
        {"lo_id": "x", "lo_name": "Jordan Lee", "rule": "least_loaded"},
        "system",
    ),
    ("support.requested", "system", {"reference": "SR-1", "topic": "other"}, "borrower"),
    (
        "application.stale",
        "system",
        {"message": "Quotes older than 21 days", "from_status": "priced", "reason": "cron"},
        "system",
    ),
    (
        "application.repriced_from_stale",
        "system",
        {"message": "Re-priced; quotes are current again"},
        "system",
    ),
    (
        "field.edited",
        _STAFF,
        {"field_key": "k", "label": "Employer", "message": "Edited Employer"},
        "staff",
    ),
    (
        "field.reverted",
        _STAFF,
        {"field_key": "k", "label": "Employer", "message": "Reverted Employer to source"},
        "staff",
    ),
    (
        "field.auto_updated",
        "system",
        {
            "field_key": "k",
            "label": "Home phone",
            "message": "Home phone follows the cell phone (auto-copied)",
        },
        "system",
    ),
    (
        "row.added",
        _STAFF,
        {"collection": "liabilities", "row_id": "r1", "message": "Added a liability"},
        "staff",
    ),
    (
        "flag.raised",
        "system",
        {
            "flag_id": "f1",
            "field_key": "k",
            "rule": "dti_max",
            "severity": "blocking",
            "tab": "credit",
            "message": "DTI over max",
        },
        "system",
    ),
    (
        "flag.resolved",
        "system",
        {
            "flag_id": "f1",
            "field_key": "k",
            "rule": "dti_max",
            "severity": "blocking",
            "tab": "credit",
            "message": "DTI over max",
        },
        "system",
    ),
    (
        "ssn.revealed",
        _STAFF,
        {"party_id": "p1", "field_key": "k", "message": "Revealed the SSN of Marcus Hale"},
        "staff",
    ),
    (
        "credit.liabilities_imported",
        _STAFF,
        {
            "imported": 3,
            "replaced": 1,
            "kept_manual": 1,
            "message": "Imported 3 liabilities from Encompass; kept 1 added by the LO",
        },
        "staff",
    ),
    (
        "credit.hard_pull_requested",
        _STAFF,
        {"consent_id": "c1", "message": "Requested borrower consent for a hard credit pull"},
        "staff",
    ),
    (
        "property.updated",
        _STAFF,
        {
            "property_id": "pr1",
            "changes": ["property type single_family"],
            "message": "Property: property type single_family",
        },
        "staff",
    ),
    (
        "document.received",
        _STAFF,
        {
            "document_id": "d1",
            "doc_type": "pay_stub",
            "received": True,
            "message": "Marked pay stub received",
        },
        "staff",
    ),
    (
        "pipeline.resume_requested",
        "system",
        {"reason": "flags_resolved", "message": "All checks pass; pricing resumed"},
        "system",
    ),
    (
        "pipeline.resume_failed",
        "system",
        {"message": "Could not resume pricing: the workflow service is unavailable"},
        "system",
    ),
]


@pytest.mark.parametrize(("event_type", "actor", "payload", "expected_kind"), _WRITTEN_EVENTS)
async def test_every_written_event_type_has_a_readable_message_and_correct_actor(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_activity_event: Callable[..., Awaitable[ActivityEvent]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
    event_type: str,
    actor: str,
    payload: dict[str, object],
    expected_kind: str,
) -> None:
    """M2: every event type actually written in the base must produce a
    non-generic, readable message and resolve to the correct actor kind --
    not the humanized `describe_event` fallback, and not a wrong or
    incorrectly-quieted actor."""
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    resolved_actor = str(owner.user.id) if actor == _STAFF else actor
    await make_activity_event(application, event_type, actor=resolved_actor, payload=payload)
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/activity")
    assert response.status_code == 200
    item = response.json()["items"][0]

    generic_fallback = event_type.replace(".", " ").replace("_", " ").capitalize()
    assert item["message"], f"{event_type} produced an empty message"
    assert item["message"] != generic_fallback, (
        f"{event_type} fell back to the generic humanized message"
    )
    assert item["actor"]["kind"] == expected_kind, (
        f"{event_type}: expected actor kind {expected_kind!r}, got {item['actor']['kind']!r}"
    )
    if expected_kind == "staff":
        assert item["actor"]["name"] == owner.user.full_name
    elif expected_kind == "borrower":
        assert item["actor"]["name"] == "Test Client"
    else:
        assert item["actor"]["name"] == "System"


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
