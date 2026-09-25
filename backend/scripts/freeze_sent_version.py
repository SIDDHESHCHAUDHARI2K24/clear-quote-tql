"""CLI to freeze a fresh, un-fixtured `QuotePackageVersion` for a persona
that has no `fixture_layer` in `seed/personas/*.yaml` (e.g. Marcus Hale) --
CQ-024's AC1 needs "a freshly sent persona" for E2E use, and
`seed/loader.py::apply_send_fixture` only runs for the two personas
(`grace_kim`, `luis_romero`) whose yaml opts into it.

**Deviation (plan.md Decision 10):** CQ-023's own dev freeze script
(`backend/scripts/freeze_version.py`, per this item's brief) is not on
this branch's base -- `git log` shows only CQ-016/021/022 merged into
`phase-p3-p4` at the time this item started. This script is a distinct
filename per the brief's own fallback instruction, so it won't collide if
CQ-023's lands later.

Reuses the exact same `freeze_package_version` factory CQ-020's real send
workflow will call (`app.features.portal.reports.versions`) -- this script
only *finds* an already-priced application's quotes and wraps them in a
`QuotePackage`; it performs no pricing math of its own. The application
must already be `priced` (run through `make demo-reset`'s pipeline, or the
Send tab / auto-price flow once those land) -- this script does not run
pricing itself.

Run via `uv run python backend/scripts/freeze_sent_version.py --persona
marcus_hale` (matches a `seed/personas/*.yaml` `key`), or `--email
marcus.hale@clearquote-demo.test` directly. Prints the report token and
each option's quote id/label.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.enums import ApplicationStatus
from app.core.security import generate_token
from app.features.applications.models import Application
from app.features.clients.models import Client
from app.features.portal.reports.versions import freeze_package_version
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage

_PERSONAS_DIR = Path(__file__).resolve().parents[2] / "seed" / "personas"


def _email_for_persona(key: str) -> str:
    for path in sorted(_PERSONAS_DIR.glob("*.yaml")):
        persona = yaml.safe_load(path.read_text())
        if persona.get("key") == key:
            email: str = persona["email"]
            return email
    raise SystemExit(f"No seed persona with key {key!r} under {_PERSONAS_DIR}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze a fresh sent QuotePackageVersion for an already-priced persona."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--persona", help="A seed/personas/*.yaml `key`, e.g. marcus_hale.")
    group.add_argument("--email", help="The client's email directly.")
    return parser.parse_args()


async def _run(email: str) -> None:
    async with AsyncSessionLocal() as db:
        client_row = (
            await db.execute(select(Client).where(Client.email == email))
        ).scalar_one_or_none()
        if client_row is None:
            raise SystemExit(f"No client with email {email!r}")

        application = (
            await db.execute(select(Application).where(Application.client_id == client_row.id))
        ).scalar_one_or_none()
        if application is None:
            raise SystemExit(f"No application for client {email!r}")

        # The pipeline's default scenario set prices its first scenario
        # group first (`_price_group`, pricing/scenarios/service.py) --
        # its quotes are the [Par, Buydown] pair the report shows.
        scenario = (
            (
                await db.execute(
                    select(Scenario)
                    .where(Scenario.application_id == application.id)
                    .order_by(Scenario.created_at.asc())
                )
            )
            .scalars()
            .first()
        )
        if scenario is None:
            raise SystemExit(
                f"No priced scenario for application {application.id} ({email!r}) -- "
                "run the pipeline (make demo-reset) first."
            )

        quotes = (
            (
                await db.execute(
                    select(Quote)
                    .where(Quote.scenario_id == scenario.id)
                    .order_by(Quote.priced_at.asc())
                )
            )
            .scalars()
            .all()
        )
        if not quotes:
            raise SystemExit(f"Scenario {scenario.id} has no quotes.")

        quote_ids = [q.id for q in quotes]
        package = QuotePackage(
            application_id=application.id,
            quote_ids=quote_ids,
            recommended_quote_id=quote_ids[0],
            report_token=generate_token(),
        )
        db.add(package)
        await db.flush()

        application.status = ApplicationStatus.SENT
        await db.flush()

        version = await freeze_package_version(db, package=package)
        await db.commit()

        print(f"application_id={application.id}")
        print(f"report_token={version.report_token}")
        for quote in quotes:
            print(f"  option {quote.label}: quote_id={quote.id}")


if __name__ == "__main__":
    args = _parse_args()
    resolved_email = args.email or _email_for_persona(args.persona)
    asyncio.run(_run(resolved_email))
