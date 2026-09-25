"""`GET /api/v1/applications` HTTP-layer tests (spec.md CQ-027).

AC1's dataset (`_seed_dataset`) is built once per test via plain ORM
inserts (no pipeline), each row's easily-checkable Python attributes kept
alongside it, so each filter's expected id set is computed directly from
those attributes -- an independent check against the query, not a second
copy of `listing.service`'s SQL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Strategy, UserRole
from app.features.applications.listing.tests.conftest import (
    MakeApplication,
    MakeLo,
    add_flag,
    add_specific_property,
    add_tbd_property,
)

_NOW = datetime(2026, 9, 25, tzinfo=UTC)


@dataclass
class Row:
    id: uuid.UUID
    status: ApplicationStatus
    strategy: Strategy | None
    price: Decimal | None
    state: str | None  # property state (specific) or one buy-box state (TBD)
    has_property: bool
    created_at: datetime
    client_name: str
    client_email: str


@pytest_asyncio.fixture
async def seed_dataset(
    db_session: AsyncSession, make_lo: MakeLo, make_application: MakeApplication
) -> tuple[list[Row], Any]:
    lo = await make_lo("Jordan Lee", UserRole.LO)

    rows: list[Row] = []

    async def _add(
        *,
        status: ApplicationStatus,
        strategy: Strategy | None,
        price: Decimal | None,
        days_ago: int,
        client_name: str,
        client_email: str,
        specific_state: str | None = None,
        tbd_states: list[str] | None = None,
        flag: bool = False,
    ) -> Row:
        created_at = _NOW - timedelta(days=days_ago)
        fixture = await make_application(
            lo=lo,
            client_name=client_name,
            client_email=client_email,
            status=status,
            strategy=strategy,
            requested_price=price,
            created_at=created_at,
            updated_at=created_at,
        )
        state: str | None = None
        has_property = False
        if specific_state is not None:
            await add_specific_property(db_session, fixture.application, state=specific_state)
            state = specific_state
            has_property = True
        elif tbd_states is not None:
            await add_tbd_property(db_session, fixture.application, buy_box_states=tbd_states)
            state = tbd_states[0]
            has_property = False
        if flag:
            await add_flag(db_session, fixture.application)
        row = Row(
            id=fixture.application.id,
            status=status,
            strategy=strategy,
            price=price,
            state=state,
            has_property=has_property,
            created_at=created_at,
            client_name=client_name,
            client_email=client_email,
        )
        rows.append(row)
        return row

    await _add(
        status=ApplicationStatus.PRICED,
        strategy=None,
        price=Decimal("200000.00"),
        days_ago=10,
        client_name="Marcus Hale",
        client_email="marcus.hale@clearquote-demo.test",
        specific_state="FL",
    )
    await _add(
        status=ApplicationStatus.PRICED,
        strategy=Strategy.STR,
        price=Decimal("500000.00"),
        days_ago=5,
        client_name="Priya Nair",
        client_email="priya.nair@clearquote-demo.test",
        specific_state="FL",
    )
    await _add(
        status=ApplicationStatus.NEEDS_ATTENTION,
        strategy=Strategy.LTR,
        price=Decimal("310000.00"),
        days_ago=2,
        client_name="Aisha Coleman",
        client_email="aisha.coleman@clearquote-demo.test",
        specific_state="OH",
        flag=True,
    )
    await _add(
        status=ApplicationStatus.SENT,
        strategy=Strategy.LTR,
        price=Decimal("330000.00"),
        days_ago=25,
        client_name="Grace Kim",
        client_email="grace.kim@clearquote-demo.test",
        specific_state="CO",
    )
    await _add(
        status=ApplicationStatus.OPTION_SELECTED,
        strategy=Strategy.STR,
        price=Decimal("450000.00"),
        days_ago=1,
        client_name="Luis Romero",
        client_email="luis.romero@clearquote-demo.test",
        tbd_states=["TX"],
    )
    await _add(
        status=ApplicationStatus.INTAKE,
        strategy=None,
        price=None,
        days_ago=0,
        client_name="Sam Reed",
        client_email="sam.reed@clearquote-demo.test",
    )
    await _add(
        status=ApplicationStatus.STALE,
        strategy=Strategy.LTR,
        price=Decimal("300000.00"),
        days_ago=30,
        client_name="Kathleen McReynolds",
        client_email="kathleen.mcreynolds@clearquote-demo.test",
        tbd_states=["FL"],
    )

    return rows, lo


async def _get(client: AsyncClient, **params: Any) -> dict[str, Any]:
    resp = await client.get("/api/v1/applications", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_status_filter_matches_expected_rows(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, status="Priced")
    expected = {r.id for r in rows if r.status == ApplicationStatus.PRICED}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected


async def test_strategy_filter_matches_expected_rows(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, strategy="str")
    expected = {r.id for r in rows if r.strategy == Strategy.STR}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected

    body = await _get(client, strategy="primary")
    expected_primary = {r.id for r in rows if r.strategy is None}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected_primary


async def test_amount_range_filter(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, amount_min="300000", amount_max="400000")
    expected = {
        r.id
        for r in rows
        if r.price is not None and Decimal("300000") <= r.price <= Decimal("400000")
    }
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected


async def test_state_filter_matches_specific_and_tbd_buy_box(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, state="FL")
    expected = {r.id for r in rows if r.state == "FL"}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected


async def test_has_property_filter(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, has_property="true")
    expected_true = {r.id for r in rows if r.has_property}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected_true

    body = await _get(client, has_property="false")
    expected_false = {r.id for r in rows if not r.has_property}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected_false


async def test_created_date_range_filter(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    created_from = (_NOW - timedelta(days=6)).date()
    created_to = (_NOW - timedelta(days=1)).date()
    body = await _get(
        client, created_from=created_from.isoformat(), created_to=created_to.isoformat()
    )
    expected = {r.id for r in rows if created_from <= r.created_at.date() <= created_to}
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected


async def test_q_filter_matches_name_and_email(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, q="aisha")
    assert {uuid.UUID(item["id"]) for item in body["items"]} == {
        r.id for r in rows if r.client_name == "Aisha Coleman"
    }

    body = await _get(client, q="grace.kim@clearquote-demo.test")
    assert {uuid.UUID(item["id"]) for item in body["items"]} == {
        r.id for r in rows if r.client_name == "Grace Kim"
    }


async def test_combined_filters(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    """AC1: three filters combined, e.g. `status=Priced&strategy=str&state=FL`."""
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, status="Priced", strategy="str", state="FL")
    expected = {
        r.id
        for r in rows
        if r.status == ApplicationStatus.PRICED and r.strategy == Strategy.STR and r.state == "FL"
    }
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected
    assert len(expected) == 1


async def test_pascal_case_comma_list_status(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    """CQ-025's tile link (`?status=Priced,Inquiry,OptionSelected`, E10)."""
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, status="Priced,Inquiry,OptionSelected")
    expected = {
        r.id
        for r in rows
        if r.status
        in {ApplicationStatus.PRICED, ApplicationStatus.INQUIRY, ApplicationStatus.OPTION_SELECTED}
    }
    assert {uuid.UUID(item["id"]) for item in body["items"]} == expected


async def test_unknown_status_is_422(client: AsyncClient, make_staff_session: Any) -> None:
    await make_staff_session(UserRole.MANAGER)
    resp = await client.get("/api/v1/applications", params={"status": "NotAStatus"})
    assert resp.status_code == 422


async def test_sort_amount_ascending(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, sort="amount", page_size=100)
    priced_rows = [item for item in body["items"] if item["purchase_price"] is not None]
    prices = [Decimal(item["purchase_price"]) for item in priced_rows]
    assert prices == sorted(prices)


async def test_default_sort_is_updated_at_desc(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, page_size=100)
    ids_in_order = [uuid.UUID(item["id"]) for item in body["items"]]
    by_updated_desc = sorted(rows, key=lambda r: r.created_at, reverse=True)
    assert ids_in_order == [r.id for r in by_updated_desc]


async def test_pagination(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, page=1, page_size=3)
    assert body["total"] == len(rows)
    assert body["page"] == 1
    assert body["page_size"] == 3
    assert len(body["items"]) == 3

    body2 = await _get(client, page=2, page_size=3)
    assert len(body2["items"]) == min(3, len(rows) - 3)

    last_page = -(-len(rows) // 3)  # ceil
    body3 = await _get(client, page=last_page, page_size=3)
    assert len(body3["items"]) == len(rows) - 3 * (last_page - 1)


async def test_needs_attention_and_tbd_personas(
    client: AsyncClient,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    """AC2: Aisha Coleman has flag_count >= 1 under `status=NeedsAttention`;
    Kathleen McReynolds (TBD property) appears labelled under
    `has_property=false`."""
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, status="NeedsAttention")
    assert len(body["items"]) == 1
    aisha = body["items"][0]
    assert aisha["client_name"] == "Aisha Coleman"
    assert aisha["flag_count"] >= 1

    body = await _get(client, has_property="false")
    kathleen = next(item for item in body["items"] if item["client_name"] == "Kathleen McReynolds")
    assert kathleen["property_label"].startswith("TBD · ")


async def test_status_stale_includes_a_fixture_set_stale(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    seed_dataset: tuple[list[Row], Any],
) -> None:
    """AC2 "status=Stale includes Grace Kim": `make demo-reset` seeds Grace
    with `status=sent` today (CQ-030's stale job, a wave-2 sibling, is what
    would flip her to `stale` -- nothing in the current seed/reset path
    calls it -- plan.md Decision #10). Verified here with a Grace-named
    fixture whose status is set to `stale` directly; the true
    `make demo-reset` -> `status=Stale` path is pending -- re-check after
    CQ-030 merges (post-dev.md)."""
    rows, _lo = seed_dataset
    await make_staff_session(UserRole.MANAGER)

    body = await _get(client, status="Stale")
    kathleen_tbd_stale = next(
        item for item in body["items"] if item["client_name"] == "Kathleen McReynolds"
    )
    assert kathleen_tbd_stale["status"] == "stale"


async def test_lo_scoping_ignores_other_lo_id(
    client: AsyncClient,
    make_staff_session: Any,
    make_lo: MakeLo,
    make_application: MakeApplication,
) -> None:
    """AC4: an LO passing another LO's `lo_id` still only gets their own
    rows. Self-contained (not the shared `seed_dataset`, which is scoped
    to a different LO): `make_staff_session` authenticates as a fresh
    staff row, so the "own" applications must belong to that same row."""
    other_lo = await make_lo("Other LO", UserRole.LO)
    other_fixture = await make_application(lo=other_lo, status=ApplicationStatus.PRICED)

    session = await make_staff_session(UserRole.LO)
    own_fixture = await make_application(lo=session.user, status=ApplicationStatus.PRICED)

    body = await _get(client, lo_id=str(other_lo.id))
    ids = {uuid.UUID(item["id"]) for item in body["items"]}

    assert ids == {own_fixture.application.id}
    assert other_fixture.application.id not in ids


async def test_lo_options_manager_sees_los_alphabetically(
    client: AsyncClient, make_staff_session: Any, make_lo: MakeLo
) -> None:
    await make_lo("Zed LO", UserRole.LO)
    await make_lo("Amy LO", UserRole.LO)
    await make_lo("Some Manager", UserRole.MANAGER)
    await make_staff_session(UserRole.MANAGER)

    resp = await client.get("/api/v1/applications/los")
    assert resp.status_code == 200
    names = [item["full_name"] for item in resp.json()]
    assert names == ["Amy LO", "Zed LO"]


async def test_lo_options_forbidden_for_lo(client: AsyncClient, make_staff_session: Any) -> None:
    await make_staff_session(UserRole.LO)
    resp = await client.get("/api/v1/applications/los")
    assert resp.status_code == 403
