"""CQ-019 AC1 + AC6 (API side): the default draft package and its edits."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.tests.test_router import _cards, _scenarios, _seed
from app.features.quotes.send.models import QuotePackage
from conftest import StaffSession

MakeStaff = Callable[..., Awaitable[StaffSession]]


async def _package(client: AsyncClient, application_id: uuid.UUID) -> dict[str, Any]:
    response = await client.get(f"/api/v1/applications/{application_id}/package")
    assert response.status_code == 200, response.text
    return response.json()


async def test_default_package_draft(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC1: Marcus Hale's first GET creates the default draft: the first
    group's Par (no recommendation yet) first, then at most 2 alternatives
    in group order; the recommendation text names down payment, pricing
    type and rate."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]

    scenarios = await _scenarios(client, application_id)
    cards = _cards(scenarios)
    package = await _package(client, application_id)

    first_par = scenarios["groups"][0]["quotes"][0]
    assert first_par["label"] == "Par"
    assert package["recommended_quote_id"] == first_par["id"]
    assert package["quote_ids"][0] == first_par["id"]
    assert len(package["quote_ids"]) == 3
    assert package["quote_ids"] == [c["id"] for c in cards][:3]

    group = scenarios["groups"][0]
    down = group["inputs"]["down_payment_pct"]
    text = package["recommendation_text"]
    assert text.startswith(f"{int(float(down) * 100)}% down · Par pricing at ")
    assert f"{first_par['rate_pct']}%" in text
    assert "5-year prepay" in text
    assert package["recipient_email"]
    assert package["attachments"] == ["Pre-approval letter (PDF)"]

    # A second GET returns the same package; no duplicate is created.
    again = await _package(client, application_id)
    assert again["id"] == package["id"]
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(QuotePackage)
            .where(QuotePackage.application_id == application_id)
        )
    ).scalar_one()
    assert count == 1


async def test_default_draft_puts_the_recommended_quote_first(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    cards = _cards(await _scenarios(client, application_id))
    starred = cards[-1]
    response = await client.post(f"/api/v1/quotes/{starred['id']}/recommend")
    assert response.status_code == 200, response.text

    package = await _package(client, application_id)
    assert package["quote_ids"][0] == starred["id"]
    assert package["recommended_quote_id"] == starred["id"]
    assert len(package["quote_ids"]) == 3
    assert "Buydown pricing" in package["recommendation_text"]


async def test_put_package_persists_and_redrafts_recommendation(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """AC6 (API): remove a quote, change the recommendation, edit the note."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    package = await _package(client, application_id)
    buydown = package["quote_ids"][1]

    body = {
        "quote_ids": [buydown, package["quote_ids"][0]],
        "recommended_quote_id": buydown,
        "lo_note": "Happy to walk you through the buydown.",
    }
    response = await client.put(f"/api/v1/applications/{application_id}/package", json=body)
    assert response.status_code == 200, response.text

    reloaded = await _package(client, application_id)
    assert reloaded["quote_ids"] == body["quote_ids"]
    assert reloaded["recommended_quote_id"] == buydown
    assert reloaded["lo_note"] == body["lo_note"]
    assert "Buydown pricing" in reloaded["recommendation_text"]

    # One recommendation per application: the builder's star follows.
    application = await db_session.get(Application, application_id, populate_existing=True)
    assert application is not None
    assert str(application.recommended_quote_id) == buydown


async def test_put_package_validation(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale", "grace_kim")
    await make_staff_session(role=UserRole.MANAGER)
    marcus = ids["marcus_hale"]
    package = await _package(client, marcus)
    grace_quote = (await _package(client, ids["grace_kim"]))["quote_ids"][0]
    url = f"/api/v1/applications/{marcus}/package"
    ours = package["quote_ids"]

    cases: list[dict[str, Any]] = [
        {"quote_ids": [ours[0], grace_quote], "recommended_quote_id": ours[0]},
        {"quote_ids": [ours[0]], "recommended_quote_id": ours[1]},
        {"quote_ids": [ours[0], ours[0]], "recommended_quote_id": ours[0]},
        {"quote_ids": ours, "recommended_quote_id": ours[0], "lo_note": "x" * 501},
        {"quote_ids": [*ours, str(uuid.uuid4())], "recommended_quote_id": ours[0]},
    ]
    for body in cases:
        response = await client.put(url, json=body)
        assert response.status_code == 422, (body, response.text)
    assert (await _package(client, marcus))["quote_ids"] == ours


async def test_package_routes_404_out_of_scope(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    package = await _package(client, ids["marcus_hale"])

    await make_staff_session(role=UserRole.LO)  # another LO
    assert (
        await client.get(f"/api/v1/applications/{ids['marcus_hale']}/package")
    ).status_code == 404
    for suffix in ("readiness", "report", "letter.html"):
        response = await client.get(f"/api/v1/packages/{package['id']}/{suffix}")
        assert response.status_code == 404, suffix
    response = await client.put(
        f"/api/v1/applications/{ids['marcus_hale']}/package",
        json={"quote_ids": [], "recommended_quote_id": None},
    )
    assert response.status_code == 404


# --- code review fixes ------------------------------------------------------


async def test_recommendation_text_follows_a_reprice(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """Quote ids survive a reprice, so the text is re-drafted from the
    recommended quote's current rate, in the package and the report."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    package = await _package(client, ids["marcus_hale"])
    await db_session.execute(
        update(Quote)
        .where(Quote.id == uuid.UUID(package["recommended_quote_id"]))
        .values(rate=Decimal("6.125"))
    )
    await db_session.commit()

    again = await _package(client, ids["marcus_hale"])
    assert "at 6.125%" in again["recommendation_text"]
    report = (await client.get(f"/api/v1/packages/{package['id']}/report")).json()
    assert report["recommendation"]["text"] == again["recommendation_text"]


async def test_draft_quote_can_be_deleted_and_leaves_the_draft(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    package = await _package(client, ids["marcus_hale"])
    first = package["quote_ids"][0]

    response = await client.delete(f"/api/v1/quotes/{first}")
    assert response.status_code == 204, response.text
    after = await _package(client, ids["marcus_hale"])
    assert first not in after["quote_ids"]
    assert after["recommended_quote_id"] == after["quote_ids"][0]


async def test_sent_package_quote_still_cannot_be_deleted(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "grace_kim")
    await make_staff_session(role=UserRole.MANAGER)
    package = await _package(client, ids["grace_kim"])
    assert package["sent_at"] is not None
    response = await client.delete(f"/api/v1/quotes/{package['quote_ids'][0]}")
    assert response.status_code == 409


async def test_default_draft_and_builder_star_share_one_recommendation(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)
    package = await _package(client, application_id)
    scenarios = await _scenarios(client, application_id)
    assert scenarios["recommended_quote_id"] == package["recommended_quote_id"]

    last = _cards(scenarios)[-1]["id"]  # not in the default draft
    assert last not in package["quote_ids"]
    response = await client.post(f"/api/v1/quotes/{last}/recommend")
    assert response.status_code == 200, response.text
    after = await _package(client, application_id)
    assert after["recommended_quote_id"] == last
    assert after["quote_ids"][0] == last
    assert len(after["quote_ids"]) == 3


# --- post-merge review round (minors) ---------------------------------------


async def test_get_package_does_not_persist_recommendation_text(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M2: a GET re-drafts the recommendation text for its own response
    only. It used to `db.commit()` the fresh text without holding
    `lock_application`, so a GET racing a PUT could overwrite the PUT's
    newer text with a stale one; now the row is left untouched."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    package = await _package(client, application_id)
    package_id = uuid.UUID(package["id"])
    stored_before = (
        await db_session.execute(
            select(QuotePackage.recommendation_text).where(QuotePackage.id == package_id)
        )
    ).scalar_one()

    await db_session.execute(
        update(Quote)
        .where(Quote.id == uuid.UUID(package["recommended_quote_id"]))
        .values(rate=Decimal("6.125"))
    )
    await db_session.commit()

    again = await _package(client, application_id)
    assert "at 6.125%" in again["recommendation_text"]  # the response is fresh

    stored_after = (
        await db_session.execute(
            select(QuotePackage.recommendation_text).where(QuotePackage.id == package_id)
        )
    ).scalar_one()
    assert stored_after == stored_before  # but the GET never wrote to the row


async def test_delete_recommended_quote_keeps_app_and_draft_recommendation_in_step(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M4: `_delete_quote_row` used to clear `applications.recommended_
    quote_id` unconditionally while `drop_quote_from_drafts` moved the
    draft's own recommendation to the quote left in its place -- the two
    disagreed. The application must follow the draft's new pick."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    package = await _package(client, application_id)
    first = package["quote_ids"][0]
    assert package["recommended_quote_id"] == first

    response = await client.delete(f"/api/v1/quotes/{first}")
    assert response.status_code == 204, response.text

    after = await _package(client, application_id)
    assert after["recommended_quote_id"] == after["quote_ids"][0]
    application = await db_session.get(Application, application_id, populate_existing=True)
    assert application is not None
    assert str(application.recommended_quote_id) == after["recommended_quote_id"]


async def test_delete_unrelated_quote_does_not_auto_assign_a_cleared_recommendation(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M4: an LO who deliberately cleared the draft's recommendation keeps
    none, even when an unrelated quote still in the draft is deleted."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    package = await _package(client, application_id)
    quote_ids = package["quote_ids"]

    response = await client.put(
        f"/api/v1/applications/{application_id}/package",
        json={"quote_ids": quote_ids, "recommended_quote_id": None},
    )
    assert response.status_code == 200, response.text

    response = await client.delete(f"/api/v1/quotes/{quote_ids[-1]}")
    assert response.status_code == 204, response.text

    after = await _package(client, application_id)
    assert after["recommended_quote_id"] is None


async def test_default_draft_logs_a_system_recommendation_event(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M4: `new_default_package` sets `applications.recommended_quote_id`
    from a GET with no user action behind it; log it like every other
    `quote.recommended` event so the timeline explains where it came
    from."""
    ids = await _seed(db_session, "marcus_hale")
    await make_staff_session(role=UserRole.MANAGER)
    application_id = ids["marcus_hale"]
    package = await _package(client, application_id)

    events = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == application_id,
                    ActivityEvent.type == "quote.recommended",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].actor == "system"
    payload = events[0].payload
    assert isinstance(payload, dict)
    assert payload["source"] == "default_draft"
    assert payload["quote_id"] == package["recommended_quote_id"]


async def test_get_or_create_package_reapplies_default_to_an_empty_unsent_draft(
    client: AsyncClient, db_session: AsyncSession, make_staff_session: MakeStaff
) -> None:
    """M5: the Send tab can be opened before any quote is priced, creating
    an unsent draft with `quote_ids=[]`. Once quotes exist, the next GET
    must apply the default instead of returning it empty forever."""
    ids = await _seed(db_session, "marcus_hale")
    application_id = ids["marcus_hale"]
    await make_staff_session(role=UserRole.MANAGER)

    db_session.add(
        QuotePackage(
            application_id=application_id,
            quote_ids=[],
            recommended_quote_id=None,
            report_token=secrets.token_urlsafe(24),
        )
    )
    await db_session.commit()

    package = await _package(client, application_id)
    assert package["quote_ids"] != []
    assert package["recommended_quote_id"] == package["quote_ids"][0]

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(QuotePackage)
            .where(QuotePackage.application_id == application_id)
        )
    ).scalar_one()
    assert count == 1  # reused the empty draft row instead of creating a second
