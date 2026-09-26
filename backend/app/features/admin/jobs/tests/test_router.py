"""CQ-030 AC7: `POST /api/v1/admin/jobs/stale-check` runs the same
`mark_stale` the scheduled activity runs and returns the counts changed;
non-admins get 403."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.quotes.stale.service import EVENT_APPLICATION_STALE

URL = "/api/v1/admin/jobs/stale-check"


async def test_admin_stale_check_endpoint(
    db_session: AsyncSession,
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[object]],
) -> None:
    users = await seed_users(db_session)
    await seed_providers(db_session)
    persona = next(p for p in load_persona_fixtures() if p["key"] == "grace_kim")
    grace_id = (
        await seed_persona(db_session, persona, lo_id=users.lo_ids[0], s3_client=None)
    ).application_id
    await make_staff_session(UserRole.ADMIN)

    first = await client.post(URL)

    assert first.status_code == 200, first.text
    body = first.json()
    assert body["applications_marked_stale"] == 1
    assert body["application_ids"] == [str(grace_id)]
    assert body["versions_expired"] == 1
    assert body["quotes_marked_stale"] > 0
    status = (
        await db_session.execute(select(Application.status).where(Application.id == grace_id))
    ).scalar_one()
    assert status is ApplicationStatus.STALE

    second = await client.post(URL)

    assert second.status_code == 200
    again = second.json()
    assert again["quotes_marked_stale"] == 0
    assert again["versions_expired"] == 0
    assert again["applications_marked_stale"] == 0
    assert again["application_ids"] == []
    events = (
        await db_session.execute(
            select(func.count())
            .select_from(ActivityEvent)
            .where(
                ActivityEvent.application_id == grace_id,
                ActivityEvent.type == EVENT_APPLICATION_STALE,
            )
        )
    ).scalar_one()
    assert events == 1


@pytest.mark.parametrize("role", [UserRole.LO, UserRole.MANAGER])
async def test_admin_stale_check_forbidden_for_non_admins(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[object]],
    role: UserRole,
) -> None:
    await make_staff_session(role)

    response = await client.post(URL)

    assert response.status_code == 403


async def test_admin_stale_check_requires_sign_in(client: AsyncClient) -> None:
    response = await client.post(URL)

    assert response.status_code == 401
