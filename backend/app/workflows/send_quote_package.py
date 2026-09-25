"""`SendQuotePackageWorkflow` (CQ-020): freeze -> render PDF -> email ->
record, one run per `POST /packages/{id}/send`.

Each activity is idempotent on the workflow id (plan.md Decision 8), so
Temporal's retries -- including a retry on another worker after this one
died mid-activity -- complete the send exactly once (AC5). When an
activity exhausts its retries (or Freeze finds the package no longer
ready), or the workflow is cancelled, the workflow records `send_status =
failed` and fails. A run that Freeze finds superseded by a newer send
(plan.md Decision 22) ends quietly and returns `""`: the package belongs to
the newer run.
"""

from __future__ import annotations

import asyncio

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from app.workflows.retry_policies import (
        ACTIVITY_TIMEOUT,
        DEFAULT_RETRY_POLICY,
        SEND_ACTIVITY_TIMEOUT,
        SEND_RETRY_POLICY,
    )
    from app.workflows.send_activities import (
        email_borrower,
        freeze_package,
        mark_send_failed,
        record_send,
        render_letter_pdf,
    )

GENERIC_FAILURE = "The send failed. Try again."
STOPPED_FAILURE = "The send stopped before finishing. Try again."
"""Also what the API reports for a send whose workflow is gone (plan.md
Decision 23)."""


def _application_error(exc: BaseException) -> ApplicationError | None:
    cause = exc.cause if isinstance(exc, ActivityError) else None
    return cause if isinstance(cause, ApplicationError) else None


def _failure_message(exc: ActivityError) -> str:
    """Only `PackageNotReadyError`'s message (the blocker list) is meant for
    the LO; anything else is logged and shown generically (PR #30 review
    minor b), so no internal detail reaches `send_error`."""
    cause = _application_error(exc)
    if cause is not None and cause.type == "PackageNotReadyError" and cause.message:
        return cause.message
    workflow.logger.warning("Send failed: %r (cause %r)", exc, exc.cause)
    return GENERIC_FAILURE


@workflow.defn
class SendQuotePackageWorkflow:
    @workflow.run
    async def run(self, package_id: str) -> str:
        workflow_id = workflow.info().workflow_id
        try:
            version_id = await workflow.execute_activity(
                freeze_package,
                args=[package_id, workflow_id],
                start_to_close_timeout=SEND_ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
            await workflow.execute_activity(
                render_letter_pdf,
                args=[version_id, workflow_id],
                start_to_close_timeout=SEND_ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
            await workflow.execute_activity(
                email_borrower,
                args=[version_id, workflow_id],
                start_to_close_timeout=SEND_ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
            await workflow.execute_activity(
                record_send,
                args=[version_id, workflow_id],
                start_to_close_timeout=SEND_ACTIVITY_TIMEOUT,
                retry_policy=SEND_RETRY_POLICY,
            )
        except (ActivityError, asyncio.CancelledError) as exc:
            if is_cancelled_exception(exc):
                message = STOPPED_FAILURE
            else:
                assert isinstance(exc, ActivityError)
                cause = _application_error(exc)
                if cause is not None and cause.type == "SendSupersededError":
                    return ""
                message = _failure_message(exc)
            await workflow.execute_activity(
                mark_send_failed,
                args=[package_id, workflow_id, message],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            raise
        return version_id
