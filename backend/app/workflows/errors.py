"""CQ-011's own named error (not one of CQ-009's `integrations/common/
errors.py` adapter errors — this is a pipeline/API-level error)."""

from __future__ import annotations

from app.core.errors import AppError


class WorkflowNotRunningError(AppError):
    """`POST /applications/{id}/pipeline/resume` when no workflow run is
    active for that application id (spec.md Contracts, API)."""

    code = "WORKFLOW_NOT_RUNNING"
    status_code = 404

    def __init__(self, application_id: str) -> None:
        super().__init__(
            f"No pipeline run is active for application {application_id}.",
            code=self.code,
            details={"application_id": application_id},
        )
        self.application_id = application_id
