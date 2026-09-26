"""`GET /api/v1/clients` role scoping (spec.md AC3): "An LO never sees
clients whose applications all belong to other LOs; a Manager sees all and
can filter by LO"."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.clients.tests.conftest import (
    MakeApplicationFor,
    MakeClient,
    MakeLo,
    add_activity_event,
    add_sent_version,
)


async def test_client_scoping_lo_only_sees_own(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    other_lo = await make_lo("Other LO", UserRole.LO)
    other_client = await make_client(lo=other_lo)
    await make_application_for(other_client.client, other_lo)

    session = await make_staff_session(UserRole.LO)
    own_client = await make_client(lo=session.user)
    await make_application_for(own_client.client, session.user)

    # A client with zero applications at all -- vacuously "all belong to
    # other LOs" (plan.md Decision 1), so invisible to a scoped LO.
    orphan = await make_client(lo=session.user)
    await db_session.flush()

    resp = await client.get("/api/v1/clients")
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}

    assert ids == {own_client.client.id}
    assert other_client.client.id not in ids
    assert orphan.client.id not in ids


async def test_client_scoping_lo_ignores_other_lo_id_param(
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    other_lo = await make_lo("Other LO", UserRole.LO)
    other_client = await make_client(lo=other_lo)
    await make_application_for(other_client.client, other_lo)

    session = await make_staff_session(UserRole.LO)
    own_client = await make_client(lo=session.user)
    await make_application_for(own_client.client, session.user)

    resp = await client.get("/api/v1/clients", params={"lo_id": str(other_lo.id)})
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert ids == {own_client.client.id}


async def test_client_scoping_manager_sees_all_and_can_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    lo_a = await make_lo("LO A", UserRole.LO)
    lo_b = await make_lo("LO B", UserRole.LO)
    client_a = await make_client(lo=lo_a)
    await make_application_for(client_a.client, lo_a)
    client_b = await make_client(lo=lo_b)
    await make_application_for(client_b.client, lo_b)
    # Zero-application client: still visible to an unscoped Manager.
    orphan = await make_client(lo=lo_a)
    await db_session.flush()

    await make_staff_session(UserRole.MANAGER)

    resp = await client.get("/api/v1/clients")
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert ids == {client_a.client.id, client_b.client.id, orphan.client.id}

    resp = await client.get("/api/v1/clients", params={"lo_id": str(lo_a.id)})
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert ids == {client_a.client.id}


async def test_client_detail_404_out_of_scope(
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    other_lo = await make_lo("Other LO", UserRole.LO)
    other_client = await make_client(lo=other_lo)
    await make_application_for(other_client.client, other_lo)

    await make_staff_session(UserRole.LO)
    resp = await client.get(f"/api/v1/clients/{other_client.client.id}")
    assert resp.status_code == 404


async def test_client_detail_404_for_unknown_id(
    client: AsyncClient, make_staff_session: Any
) -> None:
    await make_staff_session(UserRole.MANAGER)
    resp = await client.get(f"/api/v1/clients/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_client_detail_scoping_needs_active_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    """An LO CAN see a client's detail page when at least one of the
    client's applications is theirs, even if the client has other
    applications belonging to other LOs -- but only ever sees their OWN
    applications, sent versions and activity there, never the other LO's
    (critical cross-LO leak, review round 1: `get_client_detail` used to
    return every application on a shared client regardless of who was
    asking, which also leaked into the sent-versions and merged-activity
    sections since both derive from the (unscoped) application list;
    review round 2 added the sent-version/activity assertions below --
    round 1's test only asserted on `applications`)."""
    other_lo = await make_lo("Other LO", UserRole.LO)
    session = await make_staff_session(UserRole.LO)
    shared_client = await make_client(lo=session.user)
    own_app = await make_application_for(shared_client.client, session.user)
    other_app = await make_application_for(
        shared_client.client, other_lo, status=ApplicationStatus.CLOSED
    )
    own_version = await add_sent_version(db_session, own_app)
    other_version = await add_sent_version(db_session, other_app)
    own_event = await add_activity_event(db_session, own_app, type="quote.sent")
    other_event = await add_activity_event(db_session, other_app, type="quote.sent")

    resp = await client.get(f"/api/v1/clients/{shared_client.client.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    applications = body["applications"]

    assert len(applications) == 1
    assert applications[0]["id"] == str(own_app.id)
    assert applications[0]["lo_name"] == session.user.full_name
    assert not any(row["id"] == str(other_app.id) for row in applications)

    sent_version_ids = {row["id"] for row in body["sent_versions"]}
    assert sent_version_ids == {str(own_version.id)}
    assert str(other_version.id) not in sent_version_ids

    activity_ids = {row["id"] for row in body["activity"]}
    assert str(own_event.id) in activity_ids
    assert str(other_event.id) not in activity_ids


async def test_client_detail_manager_sees_every_lo_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    """A Manager/Admin still sees every application on a shared client, not
    just one LO's (spec.md: role scoping mirrors CQ-014; "Manager/Admin
    still see everything") -- including every LO's sent versions and
    activity (review round 2)."""
    lo_a = await make_lo("LO A", UserRole.LO)
    lo_b = await make_lo("LO B", UserRole.LO)
    shared_client = await make_client(lo=lo_a)
    app_a = await make_application_for(shared_client.client, lo_a)
    app_b = await make_application_for(shared_client.client, lo_b, status=ApplicationStatus.CLOSED)
    version_a = await add_sent_version(db_session, app_a)
    version_b = await add_sent_version(db_session, app_b)
    event_a = await add_activity_event(db_session, app_a, type="quote.sent")
    event_b = await add_activity_event(db_session, app_b, type="quote.sent")

    await make_staff_session(UserRole.MANAGER)
    resp = await client.get(f"/api/v1/clients/{shared_client.client.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    applications = body["applications"]

    # Each row keeps its own application's LO -- not the client's assigned
    # LO -- since the two applications here belong to different LOs.
    by_id = {row["id"]: row for row in applications}
    assert set(by_id) == {str(app_a.id), str(app_b.id)}
    assert by_id[str(app_a.id)]["lo_name"] == "LO A"
    assert by_id[str(app_b.id)]["lo_name"] == "LO B"

    sent_version_ids = {row["id"] for row in body["sent_versions"]}
    assert sent_version_ids == {str(version_a.id), str(version_b.id)}

    activity_ids = {row["id"] for row in body["activity"]}
    assert {str(event_a.id), str(event_b.id)} <= activity_ids


async def test_client_list_aggregates_scoped_to_lo_own_applications(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    """plan.md Decision (review round 1): `application_count`/
    `active_status`/`last_activity` on `GET /clients` are computed over an
    LO's own applications only, so the count/status don't reveal another
    LO's work on a shared client. A Manager sees the true, unscoped
    figures for the same client.

    Review round 2: also covers `last_activity` itself (round 1's test only
    checked `application_count`/`active_status`) -- both the raw value and
    `-last_activity` ordering must ignore the other LO's newer event."""
    now = datetime(2026, 9, 25, tzinfo=UTC)
    other_lo = await make_lo("Other LO", UserRole.LO)
    session = await make_staff_session(UserRole.LO)
    shared_client = await make_client(lo=session.user)
    # The LO's own application is terminal (closed); the other LO's is
    # still active. An unscoped aggregate would show `application_count=2`
    # and `active_status=priced` to the LO -- both would leak the other
    # LO's work.
    own_app = await make_application_for(
        shared_client.client, session.user, status=ApplicationStatus.CLOSED
    )
    other_app = await make_application_for(
        shared_client.client, other_lo, status=ApplicationStatus.PRICED
    )
    # The other LO's application has the *newer* event -- an unscoped
    # `last_activity` would surface it to this LO.
    own_event_at = now - timedelta(days=3)
    other_event_at = now - timedelta(days=1)
    await add_activity_event(db_session, own_app, at=own_event_at)
    await add_activity_event(db_session, other_app, at=other_event_at)

    # A second, wholly-owned client whose own last activity (2 days ago)
    # sits strictly between the two events above: with `last_activity`
    # correctly scoped, this client sorts ahead of `shared_client` under
    # `-last_activity` (2 days ago > 3 days ago); an unscoped
    # `shared_client.last_activity` (1 day ago, the other LO's event)
    # would wrongly sort it ahead instead.
    own_only_client = await make_client(lo=session.user)
    own_only_app = await make_application_for(own_only_client.client, session.user)
    await add_activity_event(db_session, own_only_app, at=now - timedelta(days=2))

    resp = await client.get("/api/v1/clients")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    row = next(item for item in body["items"] if item["id"] == str(shared_client.client.id))
    assert row["application_count"] == 1
    assert row["last_activity"] is not None
    assert datetime.fromisoformat(row["last_activity"]) == own_event_at

    resp = await client.get("/api/v1/clients", params={"sort": "-last_activity"})
    ids_in_order = [item["id"] for item in resp.json()["items"]]
    assert ids_in_order.index(str(own_only_client.client.id)) < ids_in_order.index(
        str(shared_client.client.id)
    )
    assert row["active_status"] is None


async def test_client_list_aggregates_unscoped_for_manager(
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    lo_a = await make_lo("LO A", UserRole.LO)
    lo_b = await make_lo("LO B", UserRole.LO)
    shared_client = await make_client(lo=lo_a)
    await make_application_for(shared_client.client, lo_a, status=ApplicationStatus.CLOSED)
    await make_application_for(shared_client.client, lo_b, status=ApplicationStatus.PRICED)

    await make_staff_session(UserRole.MANAGER)
    resp = await client.get("/api/v1/clients")
    assert resp.status_code == 200, resp.text
    row = next(item for item in resp.json()["items"] if item["id"] == str(shared_client.client.id))
    assert row["application_count"] == 2
    assert row["active_status"] == ApplicationStatus.PRICED.value


async def test_client_has_active_filter_scoped_to_lo_own_applications(
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    """Review round 2: `has_active` (like `application_count`/`active_status`/
    `last_activity`, plan.md Decision 15) must also be scoped to the
    requesting LO's own applications. LO A's own application on the shared
    client is closed (terminal); LO B's is priced (active). An unscoped
    `has_active` would show the client to LO A under `has_active=true`
    (leaking that *some* application is active, i.e. LO B's work) and hide
    it under `has_active=false` (which should be true from LO A's own
    point of view, since LO A's own application is not active)."""
    other_lo = await make_lo("Other LO", UserRole.LO)
    session = await make_staff_session(UserRole.LO)
    shared_client = await make_client(lo=session.user)
    await make_application_for(shared_client.client, session.user, status=ApplicationStatus.CLOSED)
    await make_application_for(shared_client.client, other_lo, status=ApplicationStatus.PRICED)

    resp = await client.get("/api/v1/clients", params={"has_active": "true"})
    assert resp.status_code == 200, resp.text
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert shared_client.client.id not in ids

    resp = await client.get("/api/v1/clients", params={"has_active": "false"})
    assert resp.status_code == 200, resp.text
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert shared_client.client.id in ids


async def test_client_has_active_filter_unscoped_for_manager(
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    lo_a = await make_lo("LO A", UserRole.LO)
    lo_b = await make_lo("LO B", UserRole.LO)
    shared_client = await make_client(lo=lo_a)
    await make_application_for(shared_client.client, lo_a, status=ApplicationStatus.CLOSED)
    await make_application_for(shared_client.client, lo_b, status=ApplicationStatus.PRICED)

    await make_staff_session(UserRole.MANAGER)

    resp = await client.get("/api/v1/clients", params={"has_active": "true"})
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert shared_client.client.id in ids

    resp = await client.get("/api/v1/clients", params={"has_active": "false"})
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert shared_client.client.id not in ids
