"""AC7: `POST /applications/{id}/pipeline/start` is idempotent (a second
call returns 200 without starting a second run) and `POST /applications/
{id}/pipeline/resume` returns `WorkflowNotRunningError` (404) when no run
exists.

Auth/scope (phase-p2 merge, H3): both routes require a signed-in staff user
(401 without the `cq_staff_session` cookie) and 404 (never 403, matching
CQ-015 Decision #11's style) when `application_id` isn't in that user's
`scope_applications` scope -- an LO only ever sees their own applications, a
Manager sees everyone's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from conftest import StaffSession


async def test_start_pipeline_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application()
    await db_session.commit()

    response = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_start_pipeline_404_on_other_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO -- overwrites the cookie

    response = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_owner_lo_can_start_pipeline(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=lo.user)
    await db_session.commit()

    response = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")

    assert response.status_code == 200
    assert response.json()["started"] is True


async def test_manager_can_start_pipeline_for_any_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=lo.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.MANAGER)

    response = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")

    assert response.status_code == 200
    assert response.json()["started"] is True


async def test_start_pipeline_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=lo.user)
    await db_session.commit()

    first = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")
    assert first.status_code == 200
    assert first.json()["started"] is True

    second = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")
    assert second.status_code == 200
    assert second.json()["started"] is False
    assert second.json()["workflow_id"] == first.json()["workflow_id"]


async def test_resume_pipeline_401_without_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
) -> None:
    application = await make_application()
    await db_session.commit()

    response = await client.post(f"/api/v1/applications/{application.id}/pipeline/resume")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_resume_pipeline_404_on_other_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    owner = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=owner.user)
    await db_session.commit()

    await make_staff_session(role=UserRole.LO)  # a different LO -- overwrites the cookie

    response = await client.post(f"/api/v1/applications/{application.id}/pipeline/resume")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_resume_pipeline_404s_when_no_run_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=lo.user)
    await db_session.commit()

    response = await client.post(f"/api/v1/applications/{application.id}/pipeline/resume")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "WORKFLOW_NOT_RUNNING"


async def test_resume_pipeline_signals_a_running_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=lo.user)
    await db_session.commit()

    start_response = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")
    assert start_response.status_code == 200

    resume_response = await client.post(f"/api/v1/applications/{application.id}/pipeline/resume")

    assert resume_response.status_code == 200
    assert resume_response.json()["signaled"] is True


async def test_manager_can_resume_pipeline_for_any_los_application(
    client: AsyncClient,
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    lo = await make_staff_session(role=UserRole.LO)
    application = await make_application(lo=lo.user)
    await db_session.commit()

    start_response = await client.post(f"/api/v1/applications/{application.id}/pipeline/start")
    assert start_response.status_code == 200

    await make_staff_session(role=UserRole.MANAGER)

    resume_response = await client.post(f"/api/v1/applications/{application.id}/pipeline/resume")

    assert resume_response.status_code == 200
    assert resume_response.json()["signaled"] is True
