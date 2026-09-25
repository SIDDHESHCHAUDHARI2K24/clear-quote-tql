"""Dev CLI: freeze a real sent `quote_package_versions` row for one seeded
persona, so a live `/report/{token}` page (and this item's Playwright spec)
has something real to load -- CQ-023's persona, Kathleen McReynolds, has no
`fixture_layer` in her seed YAML (she's `pipeline_end_status: priced`, not
`sent`), so `make demo-reset` never gives her one the way Grace Kim/Luis
Romero get theirs (`seed/loader.py::apply_send_fixture`). CQ-024 (borrower
actions) can reuse this for its own e2e persona.

Run via `uv run python backend/scripts/freeze_version.py --persona
kathleen_mcreynolds` from the repo root, against a worktree that has already
run `make demo-reset` (needs the persona's `Scenario`/`Quote` rows to
already exist -- runs `auto_price` itself if they don't).

Idempotent: if the persona's application already has an unexpired,
not-superseded `quote_package_versions` row whose package was frozen from
the *same* quote ids the application would resolve to right now, this
reuses it (prints its existing `report_token`) instead of freezing a new
one -- `e2e/global-setup.ts` (CQ-023) calls this on every Playwright run,
and a fresh version (and report_token) each run would be wasteful and
would leave a growing pile of superseded/expired rows in the dev DB for no
reason. The quote-id check (not just "any unexpired version exists") means
a re-price within the 21-day expiry window (a rate sheet change, a
`quote_engine` change, or a manual re-run of `auto_price`) still freezes a
fresh version instead of silently serving stale numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import uuid
from datetime import UTC, datetime

from seed.loader import load_persona_fixtures
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.features.applications.models import Application
from app.features.clients.models import Client
from app.features.portal.reports.versions import freeze_package_version
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.service import auto_price
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze a real sent quote_package_versions row for one seeded persona."
    )
    parser.add_argument("--persona", required=True, help="Persona key, e.g. kathleen_mcreynolds")
    return parser.parse_args()


async def _run(persona_key: str) -> None:
    personas = {p["key"]: p for p in load_persona_fixtures()}
    if persona_key not in personas:
        raise SystemExit(f"Unknown persona key {persona_key!r}. Known: {sorted(personas)}")
    email = personas[persona_key]["email"]

    async with AsyncSessionLocal() as db:
        client = (
            await db.execute(select(Client).where(Client.email == email))
        ).scalar_one_or_none()
        if client is None:
            raise SystemExit(f"No seeded client for {email!r} -- run `make demo-reset` first.")
        application = (
            await db.execute(select(Application).where(Application.client_id == client.id))
        ).scalar_one_or_none()
        if application is None:
            raise SystemExit(f"No application found for {email!r}.")

        scenario_ids = (
            (
                await db.execute(
                    select(Scenario.id)
                    .where(Scenario.application_id == application.id)
                    .order_by(Scenario.created_at, Scenario.id)
                )
            )
            .scalars()
            .all()
        )
        if not scenario_ids:
            print(f"No priced scenarios for {email!r} yet -- running auto_price...")
            pricing_result = await auto_price(db, application.id)
            quote_ids: list[uuid.UUID] = list(pricing_result.quote_ids)
        else:
            quotes = (
                await db.execute(
                    select(Quote.id, Quote.scenario_id, Quote.created_at)
                    .where(Quote.scenario_id.in_(scenario_ids))
                    .order_by(Quote.created_at, Quote.id)
                )
            ).all()
            quote_ids = [row.id for row in quotes]
        if not quote_ids:
            raise SystemExit(f"{email!r} has no priced quotes to freeze into a version.")

        # Idempotency check happens *after* resolving the application's
        # current quote_ids (above), not before: only reuse a version whose
        # own package was frozen from this exact quote set, so a re-price
        # since the last freeze (rate sheet change, quote_engine change, a
        # manual auto_price re-run) always gets a fresh version instead of
        # silently serving stale numbers.
        existing = (
            await db.execute(
                select(QuotePackageVersion)
                .join(QuotePackage, QuotePackageVersion.package_id == QuotePackage.id)
                .where(
                    QuotePackage.application_id == application.id,
                    QuotePackage.quote_ids == quote_ids,
                    QuotePackageVersion.superseded.is_(False),
                    QuotePackageVersion.expires_at > datetime.now(UTC),
                )
                .order_by(QuotePackageVersion.sent_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(
                f"Reusing existing quote_package_versions.id={existing.id} for {email} "
                "(unexpired, not superseded, same quote_ids as the application resolves to now)"
            )
            print(f"report_token={existing.report_token}")
            print(f"/report/{existing.report_token}")
            return

        package = QuotePackage(
            application_id=application.id,
            quote_ids=quote_ids,
            recommended_quote_id=quote_ids[0],
            report_token=secrets.token_urlsafe(24),
        )
        db.add(package)
        await db.flush()

        version = await freeze_package_version(db, package=package)
        await db.commit()

        print(f"Froze quote_package_versions.id={version.id} for {email}")
        print(f"report_token={version.report_token}")
        print(f"/report/{version.report_token}")


if __name__ == "__main__":
    asyncio.run(_run(_parse_args().persona))
