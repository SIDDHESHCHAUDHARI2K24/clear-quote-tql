"""Worker entrypoint: `python -m app.workflows.worker` connects to
`TEMPORAL_ADDRESS` (default `localhost:7233`) and registers
`ApplicationPipelineWorkflow` and its activities on the
`application-pipeline`-equivalent task queue (spec.md CQ-011). `make
worker` (root Makefile) runs the same command via `cd backend && uv run
python -m app.workflows.worker`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import get_settings
from app.workflows.activities import (
    auto_price_application,
    draft_quote_set,
    enrich_application,
    import_application,
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
ACTIVITIES: list[Callable[..., Any]] = [*CONTRACT_ACTIVITIES, record_pipeline_resumed]
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
