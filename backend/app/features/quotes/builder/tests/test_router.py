"""CQ-018 Quote Builder routes against personas seeded through the same
pipeline `make demo-reset` runs (`seed_persona`)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.service import SAME_BUCKET_NOTE
from app.features.quotes.send.models import QuotePackage
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]


async def _seed(db: AsyncSession, *keys: str) -> dict[str, uuid.UUID]:
    user_result = await seed_users(db)
    await seed_providers(db)
    personas = {p["key"]: p for p in load_persona_fixtures()}
    ids: dict[str, uuid.UUID] = {}
    for key in keys or tuple(personas):
        result = await seed_persona(db, personas[key], lo_id=user_result.lo_ids[0], s3_client=None)
        ids[key] = result.application_id
    return ids


async def _scenarios(client: AsyncClient, application_id: uuid.UUID) -> dict[str, Any]:
    response = await client.get(f"/api/v1/applications/{application_id}/scenarios")
    assert response.status_code == 200, response.text
    return response.json()


def _cards(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [card for group in body["groups"] for card in group["quotes"]]


async def test_default_scenario_groups(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC1 + AC7: the pipeline's default groups, rendered as-is."""
    ids = await _seed(
        db_session, "marcus_hale", "kathleen_mcreynolds", "priya_nair", "daniel_ortiz"
    )
    await make_staff_session(role=UserRole.MANAGER)

    marcus = await _scenarios(client, ids["marcus_hale"])
    assert marcus["strategy"] == "STR"
    assert [g["label"] for g in marcus["groups"]][0] == "At DSCR 1.00"
    assert marcus["groups"][1]["label"].startswith("At your DSCR (0.")
    assert len(marcus["groups"]) == 2
    for group in marcus["groups"]:
        assert group["note"] is None
        assert [q["label"] for q in group["quotes"]] == ["Par", "Buydown"]
        buydown = group["quotes"][1]
        assert Decimal("0") < Decimal(buydown["points_pct"]) <= Decimal("1.000")
        assert Decimal(buydown["rate_pct"]) < Decimal(group["quotes"][0]["rate_pct"])
        assert group["quotes"][0]["prepay_label"] == "5-year prepay"

    kathleen = await _scenarios(client, ids["kathleen_mcreynolds"])
    assert len(kathleen["groups"]) == 1
    assert kathleen["groups"][0]["label"] == "At DSCR 1.00"
    assert kathleen["groups"][0]["note"] == SAME_BUCKET_NOTE
    assert [q["label"] for q in kathleen["groups"][0]["quotes"]] == ["Par", "Buydown"]

    priya = await _scenarios(client, ids["priya_nair"])
    assert priya["strategy"] == "PRIMARY"
    assert [g["label"] for g in priya["groups"]] == ["At 20% down"]
    for card in _cards(priya):
        assert card["dscr_ratio"] is None
        assert card["monthly_cashflow"] is None
        assert card["prepay_label"] is None
    for group in priya["groups"]:
        assert "DSCR" not in group["label"]
        assert group["dscr_bucket"] is None

    daniel = await _scenarios(client, ids["daniel_ortiz"])
    assert [g["label"] for g in daniel["groups"]] == ["At 5% down", "At 20% down"]
    assert [q["label"] for q in daniel["groups"][1]["quotes"]] == ["Par"]
    # The 20% step removes MI (LTV <= 80%); the 5% group carries it.
    assert daniel["groups"][0]["quotes"][0]["computed"]["monthly_mi"] not in (None, "0.00")
    assert daniel["groups"][1]["quotes"][0]["computed"]["monthly_mi"] in (None, "0.00")


async def test_quote_cards_match_engine(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC2: every seeded quote's card payment and cash to close equal the
    engine output for that quote (re-run from the scenario's inputs)."""
    ids = await _seed(db_session)
    await make_staff_session(role=UserRole.MANAGER)
    checked = 0
    for application_id in ids.values():
        body = await _scenarios(client, application_id)
        for group in body["groups"]:
            scenario = await db_session.get(Scenario, uuid.UUID(group["id"]))
            assert scenario is not None and isinstance(scenario.inputs, dict)
            config = ConfigSnapshot.model_validate(scenario.config_snapshot)
            for card in group["quotes"]:
                inputs = ScenarioInputs.model_validate(scenario.inputs).model_copy(
                    update={
                        "note_rate": Decimal(card["rate_pct"]) / Decimal("100"),
                        "discount_points_pct": Decimal(card["points_pct"]) / Decimal("100"),
                    }
                )
                engine = compute_quote(inputs, config)
                assert card["monthly_payment"] == card["computed"]["total_monthly_payment"]
                assert card["cash_to_close"] == card["computed"]["cash_to_close"]
                assert Decimal(card["monthly_payment"]) == engine.total_monthly_payment
                assert Decimal(card["cash_to_close"]) == engine.cash_to_close
                assert Decimal(card["points_amount"]) == engine.discount_points_amount
                checked += 1
    assert checked >= 20


async def test_single_recommended_quote(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC5: starring sets the one recommended quote, un-stars any other, and
    the CQ-016 summary's note rate follows it; delete clears it."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    cards = _cards(await _scenarios(client, application_id))
    first, second = cards[0], cards[1]

    response = await client.post(f"/api/v1/quotes/{first['id']}/recommend")
    assert response.status_code == 200
    assert response.json()["recommended_quote_id"] == first["id"]

    response = await client.post(f"/api/v1/quotes/{second['id']}/recommend")
    assert response.status_code == 200
    body = await _scenarios(client, application_id)
    assert body["recommended_quote_id"] == second["id"]
    assert [c["id"] for c in _cards(body) if c["recommended"]] == [second["id"]]

    summary = (await client.get(f"/api/v1/applications/{application_id}/summary")).json()
    assert Decimal(summary["note_rate"]) == Decimal(second["rate_pct"])

    events = (
        (
            await db_session.execute(
                select(ActivityEvent.type).where(ActivityEvent.application_id == application_id)
            )
        )
        .scalars()
        .all()
    )
    assert events.count("quote.recommended") == 2

    response = await client.delete(f"/api/v1/quotes/{second['id']}")
    assert response.status_code == 204
    body = await _scenarios(client, application_id)
    assert body["recommended_quote_id"] is None
    assert second["id"] not in [c["id"] for c in _cards(body)]
    application = await db_session.get(Application, application_id)
    assert application is not None
    await db_session.refresh(application)
    assert application.recommended_quote_id is None


async def test_autoquote_missing_occupancy(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC6: Aisha Coleman (no occupancy in LOS) can't be priced; the 422
    names the field and its owning tab, and no quote is created."""
    ids = await _seed(db_session, "aisha_coleman")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["aisha_coleman"]
    before = await _count_quotes(db_session, application_id)

    response = await client.post(
        f"/api/v1/applications/{application_id}/scenarios",
        json={"purchase_price": "300000.00", "down_payment_pct": "0.25", "strategy": "LTR"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "missing_field"
    assert error["message"] == "Cannot price: missing Occupancy"
    assert error["details"]["field"] == "Occupancy"
    assert error["details"]["tab"] == "property"

    response = await client.post(f"/api/v1/applications/{application_id}/reprice")
    assert response.status_code == 422
    assert response.json()["error"]["details"]["field"] == "Occupancy"
    assert await _count_quotes(db_session, application_id) == before == 0


async def _count_quotes(db: AsyncSession, application_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Quote)
        .join(Scenario, Scenario.id == Quote.scenario_id)
        .where(Scenario.application_id == application_id)
    )
    return (await db.execute(stmt)).scalar_one()


async def test_autoquote_replaces(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC3 (API half): PUT 25% down then Save & AutoQuote replaces the
    scenario's Par/Buydown; the new par rate is <= the old."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][1]
    old_par = group["quotes"][0]
    assert group["inputs"]["down_payment_pct"] == "0.20"

    response = await client.put(
        f"/api/v1/scenarios/{group['id']}",
        json={
            "purchase_price": group["inputs"]["purchase_price"],
            "down_payment_pct": "0.25",
            "prepayment_penalty_years": 5,
            "lock_days": 45,
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["inputs"]["down_payment_pct"] == "0.25"
    assert updated["inputs"]["lock_days"] == 45
    assert all(q["stale"] for q in updated["quotes"])

    response = await client.post(f"/api/v1/scenarios/{group['id']}/autoquote")
    assert response.status_code == 200, response.text
    group_after = next(
        g for g in (await _scenarios(client, application_id))["groups"] if g["id"] == group["id"]
    )
    assert [q["label"] for q in group_after["quotes"]] == ["Par", "Buydown"]
    new_par = group_after["quotes"][0]
    assert new_par["down_payment_pct"] == "25.00"
    assert not new_par["stale"]
    assert Decimal(new_par["rate_pct"]) <= Decimal(old_par["rate_pct"])
    assert new_par["cash_to_close"] != old_par["cash_to_close"]

    # A second Save & AutoQuote never accumulates quotes.
    await client.post(f"/api/v1/scenarios/{group['id']}/autoquote")
    group_again = next(
        g for g in (await _scenarios(client, application_id))["groups"] if g["id"] == group["id"]
    )
    assert len(group_again["quotes"]) == 2


async def test_products_grid_and_manual_pick(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC4 (API half): the grid lists >= 8 products; a manual pick becomes
    a card with that rate; it survives a reprice (re-priced, not dropped)."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    group = (await _scenarios(client, application_id))["groups"][0]

    products = (await client.get(f"/api/v1/scenarios/{group['id']}/products")).json()
    assert len(products) >= 8
    pick = next(p for p in products if not p["is_par_rate"] and not p["is_buydown_rate"])
    response = await client.post(
        f"/api/v1/scenarios/{group['id']}/quotes", json={"product": pick, "label": "Manual"}
    )
    assert response.status_code == 200
    manual_id = response.json()["id"]
    cards = {c["id"]: c for c in _cards(await _scenarios(client, application_id))}
    assert Decimal(cards[manual_id]["rate_pct"]) == Decimal(pick["note_rate"])

    assert (await client.post(f"/api/v1/applications/{application_id}/reprice")).status_code == 200
    cards = {c["id"]: c for c in _cards(await _scenarios(client, application_id))}
    assert manual_id in cards


async def test_reprice_clears_stale(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC8 (API half): an override marks every quote stale; reprice clears
    it and moves `priced_at` forward on every quote, keeping ids stable."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    before = {c["id"]: c for c in _cards(await _scenarios(client, application_id))}

    response = await client.patch(
        f"/api/v1/applications/{application_id}/field-values/property_tax_annual_rate",
        json={"value": "0.012"},
    )
    assert response.status_code == 200, response.text
    assert all(c["stale"] for c in _cards(await _scenarios(client, application_id)))

    response = await client.post(f"/api/v1/applications/{application_id}/reprice")
    assert response.status_code == 200, response.text
    after = {c["id"]: c for c in _cards(await _scenarios(client, application_id))}
    assert set(after) == set(before)
    for quote_id, card in after.items():
        assert card["stale"] is False
        assert card["priced_at"] > before[quote_id]["priced_at"]
        # The tax override reached the repriced engine output.
        assert card["computed"]["monthly_tax"] != before[quote_id]["computed"]["monthly_tax"]
    pricing = (await client.get(f"/api/v1/applications/{application_id}/pricing")).json()
    assert pricing["has_stale_quotes"] is False


async def test_delete_quote_in_package_is_409(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    card = _cards(await _scenarios(client, application_id))[0]
    db_session.add(
        QuotePackage(
            application_id=application_id,
            quote_ids=[uuid.UUID(card["id"])],
            report_token=f"t-{uuid.uuid4()}",
        )
    )
    await db_session.flush()

    response = await client.delete(f"/api/v1/quotes/{card['id']}")
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/applications/{app}/scenarios"),
        ("POST", "/api/v1/applications/{app}/reprice"),
        ("PUT", "/api/v1/scenarios/{scenario}"),
        ("POST", "/api/v1/quotes/{quote}/recommend"),
        ("DELETE", "/api/v1/quotes/{quote}"),
    ],
)
async def test_out_of_scope_is_404(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: MakeStaff,
    method: str,
    path: str,
) -> None:
    """Decision #11: another LO's application, scenario or quote is 404."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    body = await _scenarios(client, ids["marcus_hale"])
    await make_staff_session(role=UserRole.LO)  # owns nothing
    url = path.format(
        app=ids["marcus_hale"],
        scenario=body["groups"][0]["id"],
        quote=body["groups"][0]["quotes"][0]["id"],
    )
    payload = {"purchase_price": "342000.00", "down_payment_pct": "0.25"}
    response = await client.request(method, url, json=payload if method == "PUT" else None)
    assert response.status_code == 404
