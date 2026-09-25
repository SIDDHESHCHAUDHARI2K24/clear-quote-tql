"""CLI to force-start a fresh `ApplicationPipelineWorkflow` run for an
application whose previous run already reached a terminal, *successful*
state (`priced`).

`reverify.py`'s own `_plan_resume` deliberately never repeats a completed
run ("A completed (priced) run is never repeated" -- review minor 6): only
a *failed*/terminated/cancelled/timed-out run is restarted
(`WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY`), by design -- an
application is priced once. That is correct product behaviour, but it
means an application can only be pushed through the real
verify -> enrich -> auto-price chain **once per `make demo-reset`**.

Test-only use (P5/P6 phase verification): `e2e/cross-app/p5-milestone.
spec.ts` re-demonstrates Aisha Coleman's occupancy-resume AC
(`e2e/lo-console/aisha-occupancy-resume.spec.ts`, CQ-028 AC1) as part of a
cross-item milestone. Both specs run in the same full-suite pass against
one `make demo-reset`, and `aisha-occupancy-resume.spec.ts` runs first
(alphabetically, in the `lo-console` project, which Playwright runs before
`cross-app`) -- so by the time the milestone spec reaches her, her one real
Temporal run for this demo-reset is already spent, even though her
`applications`/`flags` rows have been SQL-restored to look freshly seeded
again. This script (`WorkflowIDReusePolicy.ALLOW_DUPLICATE`, broader than
the app's own policy) gives the milestone spec a second real run, exactly
as if `make demo-reset` had just re-seeded her -- it does not change or
bypass any pricing/verification logic, only which Temporal run id is live.

Run via `uv run python backend/scripts/restart_pipeline.py --persona
aisha_coleman` (matches a `seed/personas/*.yaml` `key`), or `--email
aisha.coleman@clearquote-demo.test` directly. Prints `application_id=...`.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from sqlalchemy import select
from temporalio.common import WorkflowIDReusePolicy

from app.core.db import AsyncSessionLocal
from app.features.applications.models import Application
from app.features.clients.models import Client
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.client import get_temporal_client
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id

_PERSONAS_DIR = Path(__file__).resolve().parents[2] / "seed" / "personas"


def _email_for_persona(key: str) -> str:
    for path in sorted(_PERSONAS_DIR.glob("*.yaml")):
        persona = yaml.safe_load(path.read_text())
        if persona.get("key") == key:
            email: str = persona["email"]
            return email
    raise SystemExit(f"No seed persona with key {key!r} under {_PERSONAS_DIR}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--persona", help="seed/personas/*.yaml 'key'")
    group.add_argument("--email", help="the client's email directly")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    email = args.email or _email_for_persona(args.persona)

    async with AsyncSessionLocal() as db:
        application = (
            await db.execute(
                select(Application)
                .join(Client, Client.id == Application.client_id)
                .where(Client.email == email)
            )
        ).scalar_one()
        application_id = str(application.id)

    client = await get_temporal_client()
    workflow_id = application_workflow_id(application_id)
    await client.start_workflow(
        ApplicationPipelineWorkflow.run,
        application_id,
        id=workflow_id,
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    print(f"application_id={application_id}")


if __name__ == "__main__":
    asyncio.run(_main())
