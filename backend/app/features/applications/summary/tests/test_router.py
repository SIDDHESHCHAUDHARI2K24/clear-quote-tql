"""spec.md AC5/AC6: `GET .../summary` and `PATCH .../status` HTTP routes --
role-based access (Decision #11 style: 404, never 403, for an out-of-scope
application -- plan.md D6) and the terminal-only status transition (422 for
any value other than Withdrawn/Closed)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.applications.models import Application
from conftest import StaffSession


async def test_summary_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application()
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/summary")

    assert response.status_code == 401


async def test_summary_access_by_role(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    # The owning LO sees their own application (still the `client` fixture's
    # current cookie -- switching sessions below overwrites it).
    owner_response = await client.get(f"/api/v1/applications/{application.id}/summary")
    assert owner_response.status_code == 200

    # A different LO -- 404, never 403 (Decision #11 / plan.md D6).
    await make_staff_session(role=UserRole.LO)
    other_lo_response = await client.get(f"/api/v1/applications/{application.id}/summary")
    assert other_lo_response.status_code == 404
    assert other_lo_response.json()["error"]["code"] == "NOT_FOUND"

    # A Manager sees every application.
    await make_staff_session(role=UserRole.MANAGER)
    manager_response = await client.get(f"/api/v1/applications/{application.id}/summary")
    assert manager_response.status_code == 200
    assert manager_response.json()["application_id"] == str(application.id)


async def test_status_patch_terminal_only(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user, status=ApplicationStatus.PRICED)
    await db_session.commit()

    # Any value other than Withdrawn/Closed 422s.
    invalid = await client.patch(
        f"/api/v1/applications/{application.id}/status", json={"status": "priced"}
    )
    assert invalid.status_code == 422

    response = await client.patch(
        f"/api/v1/applications/{application.id}/status",
        json={"status": "withdrawn", "reason": "Client changed plans"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "withdrawn"


async def test_status_patch_404_for_other_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)
    response = await client.patch(
        f"/api/v1/applications/{application.id}/status", json={"status": "withdrawn"}
    )
    assert response.status_code == 404
