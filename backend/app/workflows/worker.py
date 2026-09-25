"""Worker entrypoint: `python -m app.workflows.worker` connects to
`TEMPORAL_ADDRESS` (default `localhost:7233`) and registers
`ApplicationPipelineWorkflow` and its activities on the
`application-pipeline`-equivalent task queue (spec.md CQ-011). `make
worker` (root Makefile) runs the same command from the repo root via `uv
run python -m app.workflows.worker` -- not `cd backend` first, so
Settings' env_file=".env" (backend/app/core/config.py) resolves the
repo-root .env, same as `make api`/`make test`/`make demo-reset`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

# Every feature/integration `models.py`, same list `alembic/env.py` keeps
# (its own comment explains why): a bare `python -m app.workflows.worker`
# process only ever imports the handful of modules `app.workflows.
# activities`'s own imports pull in transitively (e.g. never `app.features.
# clients.models`) -- but an activity like `import_application` writes an
# `Application` row with a `client_id` FK, and SQLAlchemy can't resolve a FK
# to a table whose mapped class was never imported into this process, no
# matter that the table exists in the real database. Without this, a real
# worker (this bug can't reproduce under pytest -- the test session's own
# `alembic upgrade head` already imports every model module first) fails
# every activity that touches a table outside that transitive set with
# `NoReferencedTableError`.
import app.features.applications.assets.models  # noqa: E402,F401
import app.features.applications.credit.models  # noqa: E402,F401
import app.features.applications.housing.models  # noqa: E402,F401
import app.features.applications.models  # noqa: E402,F401
import app.features.applications.property.models  # noqa: E402,F401
import app.features.applications.timeline.models  # noqa: E402,F401
import app.features.applications.verification.models  # noqa: E402,F401
import app.features.auth.models  # noqa: E402,F401
import app.features.borrower.consent.models  # noqa: E402,F401
import app.features.clients.models  # noqa: E402,F401
import app.features.notifications.outbox.models  # noqa: E402,F401
import app.features.pricing.scenarios.models  # noqa: E402,F401
import app.features.quotes.builder.models  # noqa: E402,F401
import app.features.quotes.send.models  # noqa: E402,F401
import app.features.settings.models  # noqa: E402,F401
import app.integrations.common.models  # noqa: E402,F401
import app.integrations.credit.models  # noqa: E402,F401
import app.integrations.crm.models  # noqa: E402,F401
import app.integrations.insurance.models  # noqa: E402,F401
import app.integrations.los.models  # noqa: E402,F401
import app.integrations.pricing.models  # noqa: E402,F401
import app.integrations.property_search.models  # noqa: E402,F401
import app.integrations.rent.models  # noqa: E402,F401
import app.integrations.str.models  # noqa: E402,F401
import app.integrations.tax.models  # noqa: E402,F401
from app.core.config import get_settings
from app.workflows.activities import (
    auto_price_application,
    draft_quote_set,
    enrich_application,
    import_application,
    load_application_source,
    record_pipeline_resumed,
    validate_pricing_inputs,
    verify_application,
)
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE

logger = logging.getLogger(__name__)

# The six activities named in spec.md's Contracts table.
CONTRACT_ACTIVITIES: list[Callable[..., Any]] = [
    import_application,
    verify_application,
    enrich_application,
    validate_pricing_inputs,
    auto_price_application,
    draft_quote_set,
]
# `record_pipeline_resumed` is an internal 7th activity (plan.md #5) the
# workflow calls when a `resume` signal is processed -- not one of the six
# contract activities, but it still has to be registered on the same task
# queue to run.
# `load_application_source` (P5/P6 foundation, E14) is another internal
# activity: the workflow's first step, deciding whether to skip the import
# stage for a portal application.
ACTIVITIES: list[Callable[..., Any]] = [
    *CONTRACT_ACTIVITIES,
    record_pipeline_resumed,
    load_application_source,
]
WORKFLOWS: list[type] = [ApplicationPipelineWorkflow]


def build_worker(client: Client) -> Worker:
    """Builds (but does not start) the worker — shared by `main()` and
    `test_worker_registration.py`, which builds one against a
    `temporalio.testing.WorkflowEnvironment` client instead of a real
    Temporal server."""
    worker = Worker(
        client,
        task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
        workflows=WORKFLOWS,
        activities=ACTIVITIES,
    )
    logger.info(
        "Registered ApplicationPipelineWorkflow and %d activities (%s) on task queue %r",
        len(CONTRACT_ACTIVITIES),
        ", ".join(fn.__name__ for fn in CONTRACT_ACTIVITIES),
        APPLICATION_PIPELINE_TASK_QUEUE,
    )
    return worker


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    logger.info(
        "Connected to Temporal at %s (namespace %s)",
        settings.temporal_address,
        settings.temporal_namespace,
    )
    worker = build_worker(client)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
