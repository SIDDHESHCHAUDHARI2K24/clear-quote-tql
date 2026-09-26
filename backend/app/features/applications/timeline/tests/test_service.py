"""Direct unit tests for `list_activity_for_applications` (review round 2,
CQ-026): merges activity across several applications for one `client`, and
takes that `client` explicitly rather than guessing it from the first
application (see the function's own docstring)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.timeline.service import list_activity_for_applications
from app.features.auth.models import User
from app.features.clients.models import Client

_NOW = datetime(2026, 9, 25, tzinfo=UTC)


async def test_merges_events_across_applications_newest_first(
    db_session: AsyncSession,
    make_lo: Callable[..., Awaitable[User]],
    make_client: Callable[..., Awaitable[Client]],
    make_application: Callable[..., Awaitable[Application]],
    make_activity_event: Callable[..., Awaitable[ActivityEvent]],
) -> None:
    lo = await make_lo()
    client = await make_client(lo)
    app_a = await make_application(lo=lo, client=client)
    app_b = await make_application(lo=lo, client=client)

    older = await make_activity_event(app_a, "pipeline.imported", at=_NOW - timedelta(days=2))
    newer = await make_activity_event(app_b, "pipeline.verified", at=_NOW - timedelta(days=1))

    events = await list_activity_for_applications(db_session, client, [app_a, app_b])

    assert [e.id for e in events] == [newer.id, older.id]


async def test_tiebreak_is_insertion_order_newest_first(
    db_session: AsyncSession,
    make_lo: Callable[..., Awaitable[User]],
    make_client: Callable[..., Awaitable[Client]],
    make_application: Callable[..., Awaitable[Application]],
    make_activity_event: Callable[..., Awaitable[ActivityEvent]],
) -> None:
    """U3 review minor: two events sharing the same `at` (a frozen
    `CLOCK_NOW`) come back in insertion order, newest first -- `created_at
    DESC` breaks the tie `at DESC` alone leaves undefined."""
    lo = await make_lo()
    client = await make_client(lo)
    app_a = await make_application(lo=lo, client=client)

    base_created = _NOW - timedelta(minutes=1)
    first = await make_activity_event(app_a, "pipeline.imported", at=_NOW, created_at=base_created)
    second = await make_activity_event(
        app_a, "pipeline.verified", at=_NOW, created_at=base_created + timedelta(seconds=1)
    )

    events = await list_activity_for_applications(db_session, client, [app_a])

    assert [e.id for e in events][:2] == [second.id, first.id]


async def test_limit_caps_the_merged_result(
    db_session: AsyncSession,
    make_lo: Callable[..., Awaitable[User]],
    make_client: Callable[..., Awaitable[Client]],
    make_application: Callable[..., Awaitable[Application]],
    make_activity_event: Callable[..., Awaitable[ActivityEvent]],
) -> None:
    lo = await make_lo()
    client = await make_client(lo)
    app_a = await make_application(lo=lo, client=client)

    for i in range(5):
        await make_activity_event(app_a, "pipeline.imported", at=_NOW - timedelta(days=i))

    events = await list_activity_for_applications(db_session, client, [app_a], limit=3)

    assert len(events) == 3


async def test_empty_applications_returns_empty(
    db_session: AsyncSession,
    make_lo: Callable[..., Awaitable[User]],
    make_client: Callable[..., Awaitable[Client]],
) -> None:
    lo = await make_lo()
    client = await make_client(lo)

    events = await list_activity_for_applications(db_session, client, [])

    assert events == []


async def test_asserts_every_application_belongs_to_client(
    db_session: AsyncSession,
    make_lo: Callable[..., Awaitable[User]],
    make_client: Callable[..., Awaitable[Client]],
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    """Review round 2: a caller bug -- an application from a *different*
    client slipping into the list -- must fail loudly instead of silently
    mislabeling the borrower name or merging in out-of-scope events."""
    lo = await make_lo()
    client = await make_client(lo)
    other_client = await make_client(lo)
    own_app = await make_application(lo=lo, client=client)
    other_app = await make_application(lo=lo, client=other_client)

    with pytest.raises(AssertionError):
        await list_activity_for_applications(db_session, client, [own_app, other_app])
