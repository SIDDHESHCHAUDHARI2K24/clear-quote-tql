"""`GET /api/v1/clients` filter/sort tests (spec.md AC2): each filter and
each sort token is checked against an expectation computed directly from
the fixtures' own Python attributes -- an independent check, not a second
copy of `clients.service`'s SQL (mirrors
`applications/listing/tests/test_router.py`)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, UserRole
from app.features.clients.tests.conftest import (
    MakeApplicationFor,
    MakeClient,
    MakeLo,
    add_activity_event,
)

_NOW = datetime(2026, 9, 25, tzinfo=UTC)


@dataclass
class Row:
    id: uuid.UUID
    name: str
    email: str
    created_at: datetime
    active: bool
    last_activity: datetime | None


@pytest_asyncio.fixture
async def dataset(
    db_session: AsyncSession,
    make_lo: MakeLo,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> tuple[list[Row], Any]:
    lo = await make_lo("Jordan Lee", UserRole.LO)
    rows: list[Row] = []

    async def _add(
        *,
        name: str,
        email: str,
        created_days_ago: int,
        status: ApplicationStatus,
        last_activity_days_ago: int | None,
    ) -> None:
        created_at = _NOW - timedelta(days=created_days_ago)
        fixture = await make_client(lo=lo, full_name=name, email=email, created_at=created_at)
        application = await make_application_for(fixture.client, lo, status=status)
        last_activity: datetime | None = None
        if last_activity_days_ago is not None:
            last_activity = _NOW - timedelta(days=last_activity_days_ago)
            await add_activity_event(db_session, application, at=last_activity)
        rows.append(
            Row(
                id=fixture.client.id,
                name=name,
                email=email,
                created_at=created_at,
                active=status not in (ApplicationStatus.WITHDRAWN, ApplicationStatus.CLOSED),
                last_activity=last_activity,
            )
        )

    await _add(
        name="Marcus Hale",
        email="marcus.hale@clearquote-demo.test",
        created_days_ago=10,
        status=ApplicationStatus.PRICED,
        last_activity_days_ago=1,
    )
    await _add(
        name="Priya Nair",
        email="priya.nair@clearquote-demo.test",
        created_days_ago=5,
        status=ApplicationStatus.NEEDS_ATTENTION,
        last_activity_days_ago=3,
    )
    await _add(
        name="Grace Kim",
        email="grace.kim@clearquote-demo.test",
        created_days_ago=25,
        status=ApplicationStatus.WITHDRAWN,
        last_activity_days_ago=20,
    )
    await _add(
        name="Aisha Coleman",
        email="aisha.coleman@clearquote-demo.test",
        created_days_ago=1,
        status=ApplicationStatus.SENT,
        last_activity_days_ago=None,
    )

    return rows, lo


async def _get(client: AsyncClient, **params: Any) -> dict[str, Any]:
    resp = await client.get("/api/v1/clients", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_client_created_date_range_filter(
    client: AsyncClient, make_staff_session: Any, dataset: tuple[list[Row], Any]
) -> None:
    rows, _lo = dataset
    await make_staff_session(UserRole.MANAGER)

    created_from = (_NOW - timedelta(days=11)).date()
    created_to = (_NOW - timedelta(days=4)).date()
    body = await _get(
        client, created_from=created_from.isoformat(), created_to=created_to.isoformat()
    )
    expected = {r.id for r in rows if created_from <= r.created_at.date() <= created_to}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected
    assert len(expected) == 2  # Marcus Hale, Priya Nair


async def test_client_has_active_filter(
    client: AsyncClient, make_staff_session: Any, dataset: tuple[list[Row], Any]
) -> None:
    rows, _lo = dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, has_active="true")
    expected_true = {r.id for r in rows if r.active}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected_true

    body = await _get(client, has_active="false")
    expected_false = {r.id for r in rows if not r.active}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected_false


@pytest.mark.parametrize(
    ("sort", "key", "reverse"),
    [
        ("name", "name", False),
        ("-created_at", "created_at", True),
    ],
)
async def test_client_sort_matches_expected_order(
    client: AsyncClient,
    make_staff_session: Any,
    dataset: tuple[list[Row], Any],
    sort: str,
    key: str,
    reverse: bool,
) -> None:
    rows, _lo = dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, sort=sort, page_size=100)
    ids_in_order = [uuid.UUID(item["id"]) for item in body["items"]]
    expected_order = [r.id for r in sorted(rows, key=lambda r: getattr(r, key), reverse=reverse)]
    assert ids_in_order == expected_order


async def test_client_sort_last_activity_nulls_last(
    client: AsyncClient, make_staff_session: Any, dataset: tuple[list[Row], Any]
) -> None:
    rows, _lo = dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, sort="-last_activity", page_size=100)
    ids_in_order = [uuid.UUID(item["id"]) for item in body["items"]]

    def _last_activity(r: Row) -> datetime:
        assert r.last_activity is not None
        return r.last_activity

    with_activity = sorted(
        (r for r in rows if r.last_activity is not None),
        key=_last_activity,
        reverse=True,
    )
    without_activity = [r for r in rows if r.last_activity is None]
    expected_order = [r.id for r in with_activity] + [r.id for r in without_activity]
    assert ids_in_order == expected_order


async def test_client_unknown_sort_is_422(client: AsyncClient, make_staff_session: Any) -> None:
    await make_staff_session(UserRole.MANAGER)
    resp = await client.get("/api/v1/clients", params={"sort": "not-a-sort"})
    assert resp.status_code == 422


async def test_client_pagination(
    client: AsyncClient, make_staff_session: Any, dataset: tuple[list[Row], Any]
) -> None:
    rows, _lo = dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, page=1, page_size=2)
    assert body["total"] == len(rows)
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
