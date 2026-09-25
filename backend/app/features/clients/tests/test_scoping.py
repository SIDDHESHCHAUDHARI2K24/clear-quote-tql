"""`GET /api/v1/clients` role scoping (spec.md AC3): "An LO never sees
clients whose applications all belong to other LOs; a Manager sees all and
can filter by LO"."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.clients.tests.conftest import MakeApplicationFor, MakeClient, MakeLo


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
    make_staff_session: Any,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    """An LO CAN see a client's detail page when at least one of the
    client's applications is theirs, even if the client has other
    applications belonging to other LOs."""
    other_lo = await make_lo("Other LO", UserRole.LO)
    session = await make_staff_session(UserRole.LO)
    shared_client = await make_client(lo=session.user)
    own_app = await make_application_for(shared_client.client, session.user)
    other_app = await make_application_for(
        shared_client.client, other_lo, status=ApplicationStatus.CLOSED
    )

    resp = await client.get(f"/api/v1/clients/{shared_client.client.id}")
    assert resp.status_code == 200, resp.text
    applications = resp.json()["applications"]
    assert len(applications) == 2

    # Each row keeps its own application's LO -- not the client's assigned
    # LO -- since the two applications here belong to different LOs.
    by_id = {row["id"]: row for row in applications}
    assert by_id[str(own_app.id)]["lo_name"] == session.user.full_name
    assert by_id[str(other_app.id)]["lo_name"] == "Other LO"
