"""`SendQuotePackageWorkflow` (CQ-020): freeze -> render PDF -> email ->
record, one run per `POST /packages/{id}/send`.

Each activity is idempotent on the workflow id (plan.md Decision 8), so
Temporal's retries -- including a retry on another worker after this one
died mid-activity -- complete the send exactly once (AC5). When an
activity exhausts its retries (or Freeze finds the package no longer
ready), the workflow records `send_status = failed` and fails.
"""

from __future__ import annotations

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.workflows.retry_policies import (
        ACTIVITY_TIMEOUT,
        DEFAULT_RETRY_POLICY,
        SEND_RETRY_POLICY,
    )
    from app.workflows.send_activities import (
        email_borrower,
        freeze_package,
        mark_send_failed,
        record_send,
        render_letter_pdf,
    )


def _failure_message(exc: ActivityError) -> str:
    cause = exc.cause
    if isinstance(cause, ApplicationError) and cause.message:
        return cause.message
    return str(cause or exc)


@workflow.defn
class SendQuotePackageWorkflow:
    @workflow.run
    async def run(self, package_id: str) -> str:
        workflow_id = workflow.info().workflow_id
        try:
            version_id = await workflow.execute_activity(
                freeze_package,
                args=[package_id, workflow_id],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
            await workflow.execute_activity(
                render_letter_pdf,
                args=[version_id, workflow_id],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
            await workflow.execute_activity(
                email_borrower,
                args=[version_id, workflow_id],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
            await workflow.execute_activity(
                record_send,
                args=[version_id, workflow_id],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
        except ActivityError as exc:
            await workflow.execute_activity(
                mark_send_failed,
                args=[package_id, workflow_id, _failure_message(exc)],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            raise
        return version_id
