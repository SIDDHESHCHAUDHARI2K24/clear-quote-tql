"""AC6: `python -m app.workflows.worker` starts, connects to Temporal, and
logs that `ApplicationPipelineWorkflow` and all six activities are
registered on the pipeline task queue; `make worker` runs the same command.

This test builds the worker with the *real* `app.workflows.worker.
build_worker` against `temporalio.testing.WorkflowEnvironment` (so CI needs
no real Temporal server) and asserts both the registration log line and
that the worker actually starts (proving `ApplicationPipelineWorkflow` and
every activity are valid Temporal definitions the SDK accepts).
"""

from __future__ import annotations

import logging

import pytest
from temporalio.testing import WorkflowEnvironment

from app.workflows import worker as worker_module
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE


async def test_build_worker_logs_registration_and_starts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.workflows.worker")
    # `alembic/env.py`'s `fileConfig(...)` (default `disable_existing_
    # loggers=True`) disables every logger already created by pytest's
    # collection-time module imports the first time the DB migration runs
    # this session (`backend/conftest.py::test_engine`) -- a project-wide
    # side effect, not specific to this logger. Undo it here so this
    # assertion doesn't depend on test collection/run order.
    logging.getLogger("app.workflows.worker").disabled = False

    # This test's own, dedicated environment/client -- not the shared
    # `temporal_client`/`temporal_worker` fixtures, whose worker polls
    # `APPLICATION_PIPELINE_TASK_QUEUE` in other tests; a second `Worker`
    # on the same client + task queue is rejected ("overlapping worker
    # task types").
    async with await WorkflowEnvironment.start_time_skipping() as env:
        worker = worker_module.build_worker(env.client)

        assert worker.task_queue == APPLICATION_PIPELINE_TASK_QUEUE
        assert "ApplicationPipelineWorkflow" in caplog.text
        for name in (
            "import_application",
            "verify_application",
            "enrich_application",
            "validate_pricing_inputs",
            "auto_price_application",
            "draft_quote_set",
        ):
            assert name in caplog.text

        async with worker:
            pass
