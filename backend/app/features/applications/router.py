"""Pipeline start/resume routes (spec.md CQ-011 "API").

`POST .../pipeline/start` is called automatically, in-process, by the
application-creation service function right after the `applications` row
commits (CQ-016/CQ-032 call that function, not this route, directly) —
this route exists for the cases spec.md calls out explicitly: an idempotent
re-trigger and this item's own endpoint tests. `POST .../pipeline/resume`
is what CQ-028's "resolve flag" UI action calls.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.features.applications.schemas import PipelineResumeResponse, PipelineStartResponse
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.client import get_temporal_client
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id
from app.workflows.errors import WorkflowNotRunningError

router = APIRouter(tags=["applications"])


@router.post("/applications/{application_id}/pipeline/start", response_model=PipelineStartResponse)
async def start_pipeline(
    application_id: uuid.UUID,
    client: Client = Depends(get_temporal_client),
) -> PipelineStartResponse:
    workflow_id = application_workflow_id(str(application_id))
    try:
        await client.start_workflow(
            ApplicationPipelineWorkflow.run,
            str(application_id),
            id=workflow_id,
            task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        return PipelineStartResponse(workflow_id=workflow_id, started=True)
    except WorkflowAlreadyStartedError:
        # A run already exists for this application id -- no-op (200, not
        # an error), spec.md AC7.
        return PipelineStartResponse(workflow_id=workflow_id, started=False)


@router.post(
    "/applications/{application_id}/pipeline/resume", response_model=PipelineResumeResponse
)
async def resume_pipeline(
    application_id: uuid.UUID,
    client: Client = Depends(get_temporal_client),
) -> PipelineResumeResponse:
    workflow_id = application_workflow_id(str(application_id))
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.signal(ApplicationPipelineWorkflow.resume)
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise WorkflowNotRunningError(str(application_id)) from exc
        raise
    return PipelineResumeResponse(workflow_id=workflow_id)
