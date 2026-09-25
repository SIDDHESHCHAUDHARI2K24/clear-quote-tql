"""CQ-018 PR review round 1 (post-dev.md): empty grids 422 instead of 500
(M2), the manual grid's Par/Buydown tags match AutoQuote (M3), the rate
ladder never moves a par (minor 1), PUT only marks stale on a real change
(minor 2), reprice logs what it deleted (minor 3), every builder write
locks the application row (minor 4), manual picks are priced server-side
(minor 5), field-specific PUT 422s (minor 6) and the same-bucket note
stays on its collapsed group (minor 7)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.service import SAME_BUCKET_NOTE
from app.features.quotes.builder.tests.test_router import _cards, _scenarios, _seed
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]

_RATE_SHEET = Path(__file__).resolve().parents[6] / "seed" / "providers" / "rate_sheet.yaml"


async def _quote_rows(db: AsyncSession, application_id: uuid.UUID) -> dict[uuid.UUID, tuple]:
    rows = (
        (
            await db.execute(
                select(Quote)
                .join(Scenario, Scenario.id == Quote.scenario_id)
                .where(Scenario.application_id == application_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    return {q.id: (q.rate, q.points, q.stale, q.priced_at, q.label) for q in rows}


def _put_body(group: dict[str, Any], **changes: Any) -> dict[str, Any]:
    body = {
        "purchase_price": group["inputs"]["purchase_price"],
        "down_payment_pct": group["inputs"]["down_payment_pct"],
        "prepayment_penalty_years": group["inputs"]["prepayment_penalty_years"],
        "lock_days": group["inputs"]["lock_days"],
        "dscr_bucket": group["dscr_bucket"],
    }
    body.update(changes)
    return body


# --- M2 ---------------------------------------------------------------------


async def test_put_with_empty_grid_is_422_and_changes_nothing(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """Investment products cap LTV at 80%: 10% down has no products."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][1]
    before = await _quote_rows(db_session, application_id)
    stored = await db_session.get(Scenario, uuid.UUID(group["id"]))
    assert stored is not None and isinstance(stored.inputs, dict)
    scenario_before = dict(stored.inputs)

    response = await client.put(
        f"/api/v1/scenarios/{group['id']}", json=_put_body(group, down_payment_pct="0.10")
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "no_eligible_products"
    assert error["message"] == "No products at 90% LTV"

    assert await _quote_rows(db_session, application_id) == before
    scenario = (
        await db_session.execute(
            select(Scenario)
            .where(Scenario.id == uuid.UUID(group["id"]))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert scenario.inputs == scenario_before


async def test_reprice_and_autoquote_with_empty_grid_are_422(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """A scenario already stored above the LTV cap (e.g. saved before an
    override) never 500s on reprice or Save & AutoQuote."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][0]
    scenario = await db_session.get(Scenario, uuid.UUID(group["id"]))
    assert scenario is not None and isinstance(scenario.inputs, dict)
    scenario.inputs = {**scenario.inputs, "down_payment_pct": "0.15"}
    await db_session.commit()
    before = await _quote_rows(db_session, application_id)

    for url in (
        f"/api/v1/applications/{application_id}/reprice",
        f"/api/v1/scenarios/{group['id']}/autoquote",
    ):
        response = await client.post(url)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "no_eligible_products"
        assert response.json()["error"]["message"] == "No products at 85% LTV"
        assert await _quote_rows(db_session, application_id) == before


async def test_create_scenario_with_empty_grid_is_422(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    response = await client.post(
        f"/api/v1/applications/{ids['marcus_hale']}/scenarios",
        json={"purchase_price": "342000.00", "down_payment_pct": "0.10", "strategy": "STR"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "no_eligible_products"


# --- M3 ---------------------------------------------------------------------


async def test_grid_tags_match_autoquote(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale", "sam_reed", "tom_lisa_brandt")
    await make_staff_session(role=UserRole.MANAGER)
    checked = 0
    for application_id in ids.values():
        for group in (await _scenarios(client, application_id))["groups"]:
            products = (await client.get(f"/api/v1/scenarios/{group['id']}/products")).json()
            by_label = {q["label"]: q for q in group["quotes"]}
            pars = [p for p in products if p["is_par_rate"]]
            buydowns = [p for p in products if p["is_buydown_rate"]]
            assert len(pars) == 1
            assert (pars[0]["investor_name"], pars[0]["product_name"]) == (
                by_label["Par"]["investor"],
                by_label["Par"]["product"],
            )
            if "Buydown" in by_label:
                assert len(buydowns) == 1
                assert (buydowns[0]["investor_name"], buydowns[0]["product_name"]) == (
                    by_label["Buydown"]["investor"],
                    by_label["Buydown"]["product"],
                )
                assert Decimal(buydowns[0]["note_rate"]) == Decimal(by_label["Buydown"]["rate_pct"])
            else:
                assert buydowns == []
            checked += 1
    assert checked >= 4


# --- minor 1 ------------------------------------------------------------------


def test_ladder_rows_never_beat_a_bucket_par() -> None:
    """Every CQ-018 ladder row sits further from par (100.000) than the
    widest bucket-specific DSCR par row (Blue Harbor Thin, 0.750)."""
    rows = yaml.safe_load(_RATE_SHEET.read_text())
    ladder = [
        r for r in rows if r["investor_name"] in ("Harborline Capital", "Keystone Investor Lending")
    ]
    assert len(ladder) == 8
    widest_par = max(
        abs(Decimal(r["base_price"]) - 100)
        for r in rows
        if r["program"] == "dscr"
        and r["dscr_bucket"] is not None
        and Decimal(r["base_price"]) >= 100
    )
    assert widest_par == Decimal("0.750")
    for row in ladder:
        assert abs(Decimal(row["base_price"]) - 100) > widest_par, row["product_name"]


async def test_below_1_00_par_is_blue_harbor_thin_for_ltr(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """A non-STR app priced in BELOW_1_00 keeps Blue Harbor Thin as par."""
    ids = await _seed(db_session, "tom_lisa_brandt")
    await make_staff_session(role=UserRole.MANAGER)
    group = (await _scenarios(client, ids["tom_lisa_brandt"]))["groups"][0]
    response = await client.put(
        f"/api/v1/scenarios/{group['id']}", json=_put_body(group, dscr_bucket="BELOW_1_00")
    )
    assert response.status_code == 200, response.text
    products = (await client.get(f"/api/v1/scenarios/{group['id']}/products")).json()
    par = next(p for p in products if p["is_par_rate"])
    assert (par["product_name"], Decimal(par["note_rate"])) == (
        "DSCR 30yr Fixed Thin",
        Decimal("7.875"),
    )


# --- minor 2 ------------------------------------------------------------------


async def test_put_without_changes_keeps_quotes_fresh(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    group = (await _scenarios(client, ids["marcus_hale"]))["groups"][0]
    response = await client.put(f"/api/v1/scenarios/{group['id']}", json=_put_body(group))
    assert response.status_code == 200, response.text
    assert not any(q["stale"] for q in response.json()["quotes"])

    response = await client.put(
        f"/api/v1/scenarios/{group['id']}", json=_put_body(group, lock_days=45)
    )
    assert all(q["stale"] for q in response.json()["quotes"])


# --- minor 3 ------------------------------------------------------------------


async def test_reprice_logs_deleted_auto_quotes(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][0]
    par = group["quotes"][0]
    # A leftover duplicate Par, recommended.
    duplicate = Quote(
        scenario_id=uuid.UUID(group["id"]),
        investor=par["investor"],
        product=par["product"],
        rate=Decimal(par["rate_pct"]),
        points=Decimal("0"),
        lock_days=par["lock_days"],
        computed=par["computed"],
        label="Par",
        priced_at=datetime.now(UTC),
        # Tests share one transaction (`now()` is fixed): order it after the
        # pipeline's Par explicitly, so the duplicate is the one removed.
        created_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    db_session.add(duplicate)
    await db_session.flush()
    application = await db_session.get(Application, application_id)
    assert application is not None
    application.recommended_quote_id = duplicate.id
    await db_session.commit()
    duplicate_id = duplicate.id

    response = await client.post(f"/api/v1/applications/{application_id}/reprice")
    assert response.status_code == 200, response.text
    event_row = (
        await db_session.execute(
            select(ActivityEvent).where(
                ActivityEvent.application_id == application_id,
                ActivityEvent.type == "quotes.repriced",
            )
        )
    ).scalar_one()
    payload = event_row.payload
    assert isinstance(payload, dict)
    assert payload["deleted_quote_ids"] == [str(duplicate_id)]
    assert payload["recommendation_cleared"] is True


# --- minor 4 ------------------------------------------------------------------


@contextmanager
def _capture_sql() -> Iterator[list[str]]:
    statements: list[str] = []

    def _listener(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", _listener)


def _locks_application(statements: list[str]) -> bool:
    return any(
        "FROM applications" in s and "FOR UPDATE" in s and "quotes" not in s.split("FROM")[0]
        for s in statements
    )


async def test_every_builder_write_locks_the_application_row(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """Row lock first, so an override committing mid-reprice waits (and
    marks stale after), and a double Save & AutoQuote can't insert two Pars."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][0]
    buydown = group["quotes"][1]
    calls: list[tuple[str, str, dict[str, Any] | None]] = [
        ("POST", f"/api/v1/applications/{application_id}/reprice", None),
        ("POST", f"/api/v1/scenarios/{group['id']}/autoquote", None),
        ("PUT", f"/api/v1/scenarios/{group['id']}", _put_body(group, lock_days=45)),
        ("POST", f"/api/v1/quotes/{buydown['id']}/recommend", None),
        (
            "PATCH",
            f"/api/v1/applications/{application_id}/field-values/property_tax_annual_rate",
            {"value": "0.012"},
        ),
        (
            "POST",
            f"/api/v1/applications/{application_id}/field-values/property_tax_annual_rate/revert",
            None,
        ),
        ("DELETE", f"/api/v1/quotes/{buydown['id']}", None),
    ]
    for method, url, body in calls:
        with _capture_sql() as statements:
            response = await client.request(method, url, json=body)
        assert response.status_code in (200, 204), (url, response.text)
        assert _locks_application(statements), url


# --- minor 5 ------------------------------------------------------------------


async def test_manual_pick_uses_server_row(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    group = (await _scenarios(client, ids["marcus_hale"]))["groups"][0]
    products = (await client.get(f"/api/v1/scenarios/{group['id']}/products")).json()
    pick = next(p for p in products if p["product_name"] == "DSCR 30yr Fixed Max Credit")

    tampered = {**pick, "note_rate": "3.000", "discount_points_pct": "0.00000"}
    response = await client.post(
        f"/api/v1/scenarios/{group['id']}/quotes", json={"product": tampered, "label": "Manual"}
    )
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["rate"]) == Decimal(pick["note_rate"])
    assert Decimal(response.json()["points"]) == Decimal(pick["discount_points_pct"]).quantize(
        Decimal("0.001")
    )

    unknown = {**pick, "product_name": "Not On The Grid"}
    response = await client.post(
        f"/api/v1/scenarios/{group['id']}/quotes", json={"product": unknown, "label": "Manual"}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "product_not_offered"


# --- minor 6 ------------------------------------------------------------------


async def test_put_422s(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "priya_nair", "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    priya = (await _scenarios(client, ids["priya_nair"]))["groups"][0]
    url = f"/api/v1/scenarios/{priya['id']}"

    response = await client.put(url, json=_put_body(priya, down_payment_pct="1.5"))
    assert response.status_code == 422
    assert "down_payment_pct" in str(response.json())

    response = await client.put(url, json=_put_body(priya, dscr_bucket="GE_1_25"))
    assert response.status_code == 422
    assert response.json()["error"]["details"]["field"] == "dscr_bucket"

    response = await client.put(url, json=_put_body(priya, prepayment_penalty_years=5))
    assert response.status_code == 422
    assert response.json()["error"]["details"]["field"] == "prepayment_penalty_years"

    marcus_id = ids["marcus_hale"]
    marcus = (await _scenarios(client, marcus_id))["groups"][0]
    application = await db_session.get(Application, marcus_id)
    assert application is not None
    application.occupancy = None
    await db_session.commit()
    response = await client.put(f"/api/v1/scenarios/{marcus['id']}", json=_put_body(marcus))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_field"
    assert response.json()["error"]["details"]["field"] == "Occupancy"


# --- minor 7 ------------------------------------------------------------------


@pytest.mark.parametrize("persona", ["kathleen_mcreynolds"])
async def test_same_bucket_note_survives_an_added_scenario(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff, persona: str
) -> None:
    ids = await _seed(db_session, persona)
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids[persona]
    body = await _scenarios(client, application_id)
    assert [g["note"] for g in body["groups"]] == [SAME_BUCKET_NOTE]
    collapsed_id = body["groups"][0]["id"]

    response = await client.post(
        f"/api/v1/applications/{application_id}/scenarios",
        json={
            "purchase_price": body["groups"][0]["inputs"]["purchase_price"],
            "down_payment_pct": "0.30",
            "strategy": body["strategy"],
        },
    )
    assert response.status_code == 200, response.text
    # Tests share one transaction, so `now()` is fixed: date the LO's
    # scenario after the pipeline's, as a later request would.
    added = await db_session.get(Scenario, uuid.UUID(response.json()["id"]))
    assert added is not None
    added.created_at = datetime.now(UTC) + timedelta(minutes=1)
    await db_session.commit()
    body = await _scenarios(client, application_id)
    assert len(body["groups"]) == 2
    notes = {g["id"]: g["note"] for g in body["groups"]}
    assert notes[collapsed_id] == SAME_BUCKET_NOTE
    assert [n for i, n in notes.items() if i != collapsed_id] == [None]
    assert len(_cards(body)) >= 2


async def test_manual_pick_after_override_uses_fresh_inputs(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """Code review: with "Choose manually" skipping the no-op PUT, the pick
    itself must re-read enrichment inputs (a tax override since the last
    save) instead of pricing from the stored ones."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][0]
    old_tax = group["quotes"][0]["computed"]["monthly_tax"]
    response = await client.patch(
        f"/api/v1/applications/{application_id}/field-values/property_tax_annual_rate",
        json={"value": "0.012"},
    )
    assert response.status_code == 200, response.text

    products = (await client.get(f"/api/v1/scenarios/{group['id']}/products")).json()
    pick = next(p for p in products if p["product_name"] == "DSCR 30yr Fixed Max Credit")
    response = await client.post(
        f"/api/v1/scenarios/{group['id']}/quotes", json={"product": pick, "label": "Manual"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["computed"]["monthly_tax"] != old_tax
