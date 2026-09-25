"""AC3: `import_application`/`enrich_application` retry up to 3 times on a
transient error and give up (surfacing to the workflow) on the 3rd;
`PricingValidationError`/`ProviderUnavailableError` are never retried.

Uses a pair of tiny throwaway single-activity workflows executing the
*real* `import_application`/`enrich_application` activities with the real
`IMPORT_ENRICH_RETRY_POLICY` from `app.workflows.retry_policies`, on their
own task queue — `temporal_env`'s time-skipping means the 1s/2s/4s backoff
schedule resolves near-instantly in wall-clock terms.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ActivityError
from temporalio.worker import Worker

from app.features.applications.models import Application
from app.integrations.common.errors import ProviderUnavailableError
from app.workflows import activities
from app.workflows.retry_policies import (
    SEND_ACTIVITY_TIMEOUT,
    SEND_EXECUTION_TIMEOUT,
    SEND_RETRY_POLICY,
)
from app.workflows.send_quote_package import SendQuotePackageWorkflow
from app.workflows.tests._retry_workflows import EnrichRetryWorkflow, ImportRetryWorkflow
from app.workflows.tests.conftest import install_import_from_los

_TASK_QUEUE = "cq-011-test-retry"


@pytest_asyncio.fixture
async def retry_test_worker(temporal_client: Client) -> AsyncIterator[Worker]:
    worker = Worker(
        temporal_client,
        task_queue=_TASK_QUEUE,
        workflows=[ImportRetryWorkflow, EnrichRetryWorkflow],
        activities=[activities.import_application, activities.enrich_application],
    )
    async with worker:
        yield worker


async def test_import_application_retries_transient_error_up_to_3_times(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
    temporal_client: Client,
    retry_test_worker: Worker,
) -> None:
    application = await make_persona_application()
    call_count = 0

    async def _flaky(application_id: uuid.UUID, db: AsyncSession) -> None:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("transient mock-adapter latency")

    install_import_from_los(monkeypatch, _flaky)

    with pytest.raises(WorkflowFailureError) as excinfo:
        await temporal_client.execute_workflow(
            ImportRetryWorkflow.run,
            str(application.id),
            id=f"retry-import-transient-{uuid.uuid4()}",
            task_queue=_TASK_QUEUE,
        )
    assert isinstance(excinfo.value.cause, ActivityError)
    assert call_count == 3


async def test_import_application_never_retries_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
    temporal_client: Client,
    retry_test_worker: Worker,
) -> None:
    application = await make_persona_application()
    call_count = 0

    async def _unavailable(application_id: uuid.UUID, db: AsyncSession) -> None:
        nonlocal call_count
        call_count += 1
        raise ProviderUnavailableError("los")

    install_import_from_los(monkeypatch, _unavailable)

    with pytest.raises(WorkflowFailureError) as excinfo:
        await temporal_client.execute_workflow(
            ImportRetryWorkflow.run,
            str(application.id),
            id=f"retry-import-nonretry-{uuid.uuid4()}",
            task_queue=_TASK_QUEUE,
        )
    assert isinstance(excinfo.value.cause, ActivityError)
    assert call_count == 1


async def test_enrich_application_retries_transient_error_up_to_3_times(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
    temporal_client: Client,
    retry_test_worker: Worker,
) -> None:
    application = await make_persona_application()
    call_count = 0

    async def _flaky(db: AsyncSession, application_id: uuid.UUID) -> None:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("transient mock-adapter latency")

    monkeypatch.setattr(activities, "enrich_pricing_fields", _flaky)

    with pytest.raises(WorkflowFailureError) as excinfo:
        await temporal_client.execute_workflow(
            EnrichRetryWorkflow.run,
            str(application.id),
            id=f"retry-enrich-transient-{uuid.uuid4()}",
            task_queue=_TASK_QUEUE,
        )
    assert isinstance(excinfo.value.cause, ActivityError)
    assert call_count == 3


async def test_enrich_application_never_retries_pricing_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    make_persona_application: Callable[..., Awaitable[Application]],
    temporal_client: Client,
    retry_test_worker: Worker,
) -> None:
    from app.integrations.common.errors import PricingValidationError

    application = await make_persona_application()
    call_count = 0

    async def _invalid(db: AsyncSession, application_id: uuid.UUID) -> None:
        nonlocal call_count
        call_count += 1
        raise PricingValidationError(["Occupancy"])

    monkeypatch.setattr(activities, "enrich_pricing_fields", _invalid)

    with pytest.raises(WorkflowFailureError) as excinfo:
        await temporal_client.execute_workflow(
            EnrichRetryWorkflow.run,
            str(application.id),
            id=f"retry-enrich-nonretry-{uuid.uuid4()}",
            task_queue=_TASK_QUEUE,
        )
    assert isinstance(excinfo.value.cause, ActivityError)
    assert call_count == 1


# --- CQ-020 PR #30 re-review minor 3: the send retry budget must fit -------


def _worst_case_activity_budget(
    *,
    attempts: int,
    activity_timeout: timedelta,
    backoff_coefficient: float,
    initial_interval: timedelta,
    maximum_interval: timedelta,
) -> timedelta:
    """The longest a single activity can spend before its retries are
    exhausted: every attempt burns its full `start_to_close_timeout`
    (the worst case -- a hung dependency, not a fast failure), plus the
    backoff wait before each retry after the first attempt."""
    total = activity_timeout * attempts
    interval = initial_interval
    for _ in range(attempts - 1):
        total += min(interval, maximum_interval)
        interval *= backoff_coefficient
    return total


def test_send_execution_timeout_exceeds_the_worst_case_retry_budget() -> None:
    """`SendQuotePackageWorkflow` (`app/workflows/send_quote_package.py`)
    runs freeze/render/email/record under `SEND_RETRY_POLICY` and
    `SEND_ACTIVITY_TIMEOUT`. If Temporal only exhausts a *later* one of
    those activities' retries after the earlier ones each also burned their
    own worst-case retry budget (transient failures that each eventually
    clear), the workflow's `except` block -- and therefore
    `mark_send_failed` -- must still get to run before
    `SEND_EXECUTION_TIMEOUT` cuts the whole workflow off; a run timed out by
    Temporal's execution timeout never reaches `except`, so the package
    stays stuck "in flight" instead of `failed` (plan.md Decision 23's
    `reconcile_send` is the fallback for that, but it depends on a later
    poll -- this invariant means it's rarely needed for a merely-slow send).

    Before this fix, `SEND_ACTIVITY_TIMEOUT` didn't exist (the shared 60s
    `ACTIVITY_TIMEOUT` was used instead): one activity's worst case was
    5*60 + (1+2+4+8) = 315s, so all four together could add up to 1260s
    (21 min) -- more than double `SEND_EXECUTION_TIMEOUT` (10 min)."""
    source = inspect.getsource(SendQuotePackageWorkflow.run)
    send_activity_count = source.count("retry_policy=SEND_RETRY_POLICY")
    assert send_activity_count > 0  # the workflow still uses SEND_RETRY_POLICY somewhere

    # `RetryPolicy.maximum_interval` is `None` only when the policy doesn't
    # set one; `SEND_RETRY_POLICY` always does.
    assert SEND_RETRY_POLICY.maximum_interval is not None
    one_activity = _worst_case_activity_budget(
        attempts=SEND_RETRY_POLICY.maximum_attempts,
        activity_timeout=SEND_ACTIVITY_TIMEOUT,
        backoff_coefficient=SEND_RETRY_POLICY.backoff_coefficient,
        initial_interval=SEND_RETRY_POLICY.initial_interval,
        maximum_interval=SEND_RETRY_POLICY.maximum_interval,
    )
    worst_case_total = one_activity * send_activity_count

    assert SEND_EXECUTION_TIMEOUT > worst_case_total, (
        f"SEND_EXECUTION_TIMEOUT ({SEND_EXECUTION_TIMEOUT}) must exceed the worst-case "
        f"retry budget of the {send_activity_count} SEND_RETRY_POLICY activities "
        f"({worst_case_total}), or a persistently failing step can be timed out by "
        "Temporal before mark_send_failed ever runs."
    )
