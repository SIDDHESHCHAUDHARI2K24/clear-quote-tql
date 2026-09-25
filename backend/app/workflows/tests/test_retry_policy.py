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

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ActivityError
from temporalio.worker import Worker

from app.features.applications.models import Application
from app.integrations.common.errors import ProviderUnavailableError
from app.workflows import activities
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
