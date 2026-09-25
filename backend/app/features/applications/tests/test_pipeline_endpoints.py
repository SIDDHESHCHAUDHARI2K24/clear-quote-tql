"""AC7: `POST /applications/{id}/pipeline/start` is idempotent (a second
call returns 200 without starting a second run) and `POST /applications/
{id}/pipeline/resume` returns `WorkflowNotRunningError` (404) when no run
exists.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_start_pipeline_is_idempotent(client: AsyncClient) -> None:
    application_id = uuid.uuid4()

    first = await client.post(f"/api/v1/applications/{application_id}/pipeline/start")
    assert first.status_code == 200
    assert first.json()["started"] is True

    second = await client.post(f"/api/v1/applications/{application_id}/pipeline/start")
    assert second.status_code == 200
    assert second.json()["started"] is False
    assert second.json()["workflow_id"] == first.json()["workflow_id"]


async def test_resume_pipeline_404s_when_no_run_exists(client: AsyncClient) -> None:
    application_id = uuid.uuid4()

    response = await client.post(f"/api/v1/applications/{application_id}/pipeline/resume")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "WORKFLOW_NOT_RUNNING"


async def test_resume_pipeline_signals_a_running_workflow(client: AsyncClient) -> None:
    application_id = uuid.uuid4()

    start_response = await client.post(f"/api/v1/applications/{application_id}/pipeline/start")
    assert start_response.status_code == 200

    resume_response = await client.post(f"/api/v1/applications/{application_id}/pipeline/resume")

    assert resume_response.status_code == 200
    assert resume_response.json()["signaled"] is True
