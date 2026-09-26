"""`GET /api/v1/clients/{id}` on a real seeded persona (spec.md AC4): same
seed loader `make demo-reset` runs (mirrors
`quotes/stale/tests/test_service.py`'s own `_seed` pattern)."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from seed.loader import (
    apply_send_fixture,
    load_persona_fixtures,
    seed_persona,
    seed_providers,
    seed_users,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.applications.models import Application
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote


async def test_client_detail_marcus_hale(
    db_session: AsyncSession, client: AsyncClient, make_staff_session: Any
) -> None:
    """AC4: Marcus Hale's detail page lists his application, his sent
    version with the recommended option, and his timeline newest-first."""
    users = await seed_users(db_session)
    await seed_providers(db_session)
    personas = {p["key"]: p for p in load_persona_fixtures()}

    result = await seed_persona(
        db_session, personas["marcus_hale"], lo_id=users.lo_ids[0], s3_client=None
    )
    application = await db_session.get(Application, result.application_id)
    assert application is not None

    quotes = (
        (
            await db_session.execute(
                select(Quote)
                .join(Scenario, Quote.scenario_id == Scenario.id)
                .where(Scenario.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    assert quotes, "Marcus Hale's persona must price cleanly for this fixture to be meaningful"

    await apply_send_fixture(
        db_session,
        application_id=application.id,
        sent_days_ago=2,
        viewed_days_ago=1,
        borrower_action=None,
        borrower_email="marcus.hale@clearquote-demo.test",
    )

    await make_staff_session(UserRole.MANAGER)
    resp = await client.get(f"/api/v1/clients/{application.client_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["name"] == "Marcus Hale"
    assert body["email"] == "marcus.hale@clearquote-demo.test"

    assert len(body["applications"]) == 1
    assert body["applications"][0]["id"] == str(application.id)

    assert len(body["sent_versions"]) == 1
    sent_version = body["sent_versions"][0]
    assert sent_version["application_id"] == str(application.id)
    assert sent_version["status"] == "viewed"
    assert sent_version["recommended_option_label"]
    assert "/report/" in sent_version["report_link"]
    assert sent_version["report_link"].startswith("http")

    assert len(body["activity"]) > 0
    ats = [item["at"] for item in body["activity"]]
    assert ats == sorted(ats, reverse=True), "newest first (AC4)"


async def test_client_detail_lo_scoping_hides_marcus_from_other_lo(
    db_session: AsyncSession, client: AsyncClient, make_staff_session: Any
) -> None:
    users = await seed_users(db_session)
    await seed_providers(db_session)
    personas = {p["key"]: p for p in load_persona_fixtures()}
    result = await seed_persona(
        db_session, personas["marcus_hale"], lo_id=users.lo_ids[0], s3_client=None
    )
    application = await db_session.get(Application, result.application_id)
    assert application is not None

    # A different, freshly-created LO (not `users.lo_ids[0]`) never had a
    # Marcus Hale application, so the client is out of their scope.
    await make_staff_session(UserRole.LO)
    resp = await client.get(f"/api/v1/clients/{application.client_id}")
    assert resp.status_code == 404
