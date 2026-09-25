"""CQ-020 send service: starts `SendQuotePackageWorkflow`, reports its
progress, lists sent versions and streams their letter PDFs.

Scoping: every entry point takes a package already resolved by
`get_scoped_package` (404 out of scope, Decision #11 / D6; plan.md
Decision 1).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client as TemporalClient
from temporalio.client import WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError, RPCStatusCode

from app.core import storage
from app.core.errors import AppError, ConflictError, NotFoundError
from app.features.applications.models import Application
from app.features.clients.models import Client
from app.features.notifications.outbox.models import OutboxEmail
from app.features.quotes.delivery.schemas import SendStarted, SendStatus, SentVersion
from app.features.quotes.delivery.steps import report_url
from app.features.quotes.send.models import (
    IN_FLIGHT_SEND_STATUSES,
    QuotePackage,
    QuotePackageVersion,
)
from app.features.quotes.send.models import SendStatus as SendStep
from app.features.quotes.send.readiness import send_blockers
from app.features.quotes.send.schemas import ReadinessBlocker
from app.workflows.client import TemporalProvider
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, send_workflow_id
from app.workflows.retry_policies import SEND_EXECUTION_TIMEOUT
from app.workflows.send_quote_package import STOPPED_FAILURE, SendQuotePackageWorkflow

logger = logging.getLogger(__name__)


class PackageNotReadyConflict(ConflictError):
    code = "PACKAGE_NOT_READY"


class SendUnavailableError(AppError):
    code = "SEND_UNAVAILABLE"
    status_code = 503


async def _lock_package(db: AsyncSession, package_id: uuid.UUID) -> QuotePackage:
    return (
        await db.execute(
            select(QuotePackage)
            .where(QuotePackage.id == package_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _workflow_running(temporal: TemporalClient, workflow_id: str) -> bool:
    try:
        description = await temporal.get_workflow_handle(workflow_id).describe()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
    return description.status == WorkflowExecutionStatus.RUNNING


async def _send_is_alive(temporal: TemporalClient, workflow_id: str) -> bool:
    """False only when Temporal says the workflow is gone (finished without
    writing `done`/`failed`: terminated, timed out, never started). When
    Temporal can't be reached, the send is given the benefit of the doubt."""
    try:
        return await _workflow_running(temporal, workflow_id)
    except Exception:
        logger.warning("Could not check send workflow %s", workflow_id, exc_info=True)
        return True


async def reconcile_send(
    db: AsyncSession, package: QuotePackage, temporal: TemporalProvider
) -> QuotePackage:
    """plan.md Decision 23: a package whose send looks in flight but whose
    workflow is gone (terminated, cancelled before it ran, timed out with no
    worker) is marked `failed`, so it never stays locked. Returns the
    package re-read from the DB. Does not commit: the caller does, together
    with whatever else it writes. Takes the row lock only when it has to
    write (a caller that already holds it keeps it)."""
    package = (
        await db.execute(
            select(QuotePackage)
            .where(QuotePackage.id == package.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    workflow_id = package.send_workflow_id
    if package.send_status not in IN_FLIGHT_SEND_STATUSES or workflow_id is None:
        return package
    if await _send_is_alive(await temporal(), workflow_id):
        return package
    package = await _lock_package(db, package.id)
    if package.send_workflow_id == workflow_id and package.send_status in IN_FLIGHT_SEND_STATUSES:
        logger.warning("Send %s is gone from Temporal; marking it failed", workflow_id)
        package.send_status = SendStep.FAILED.value
        package.send_error = STOPPED_FAILURE
        await db.flush()
    return package


async def start_send(
    db: AsyncSession, package: QuotePackage, temporal: TemporalClient
) -> SendStarted:
    """`POST /packages/{id}/send`: 409 with the blocker list when not ready
    (AC4, nothing is written or started); otherwise starts the workflow
    and records its id as `queued` (plan.md Decision 9).

    plan.md Decision 22: the workflow is started *while the package row
    lock is held*, and the new id is committed only after Temporal has
    accepted it. A second POST waiting on the lock therefore always finds a
    workflow Temporal knows about, so it answers with that id instead of
    minting a second send. (Freeze also refuses a run that isn't the
    package's current send, as a second line of defence.)"""
    package = await _lock_package(db, package.id)
    if (
        package.send_status in IN_FLIGHT_SEND_STATUSES
        and package.send_workflow_id is not None
        and await _workflow_running(temporal, package.send_workflow_id)
    ):
        # Double click: the running send answers; nothing new starts. The
        # row lock is released when the request's session closes.
        return SendStarted(
            package_id=package.id,
            workflow_id=package.send_workflow_id,
            status=package.send_status,  # type: ignore[arg-type]
        )

    blockers = await send_blockers(db, package)
    if blockers:
        raise PackageNotReadyConflict(
            "The package isn't ready to send.",
            details={
                "blockers": [
                    ReadinessBlocker(code=b.code, message=b.message, tab=b.tab).model_dump()
                    for b in blockers
                ]
            },
        )

    workflow_id = send_workflow_id(str(package.id), uuid.uuid4().hex)
    try:
        await temporal.start_workflow(
            SendQuotePackageWorkflow.run,
            str(package.id),
            id=workflow_id,
            task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            execution_timeout=SEND_EXECUTION_TIMEOUT,
        )
    except Exception as exc:
        # Still under the lock: nothing else wrote the package meanwhile.
        package.send_workflow_id = workflow_id
        package.send_status = SendStep.FAILED.value
        package.send_error = "The send could not be started."
        await db.commit()
        raise SendUnavailableError("The send could not be started. Try again.") from exc
    # Freeze waits on this lock, so it always sees the committed id.
    package.send_workflow_id = workflow_id
    package.send_status = SendStep.QUEUED.value
    package.send_error = None
    await db.commit()
    return SendStarted(package_id=package.id, workflow_id=workflow_id, status="queued")


async def _recipient(db: AsyncSession, package: QuotePackage) -> str | None:
    application = await db.get(Application, package.application_id)
    assert application is not None
    client_row = await db.get(Client, application.client_id)
    email = (client_row.email if client_row is not None else "") or ""
    return email.strip() or None


async def send_status(
    db: AsyncSession, package: QuotePackage, temporal: TemporalProvider
) -> SendStatus:
    """`GET /send-status`. DB-backed (plan.md Decision 7); asks Temporal
    only while the send looks in flight, to report a dead one as `failed`
    (Decision 23)."""
    package = await reconcile_send(db, package, temporal)
    await db.commit()  # keeps a `failed` it wrote; ends the read
    version = None
    if package.send_workflow_id is not None:
        version = (
            await db.execute(
                select(QuotePackageVersion).where(
                    QuotePackageVersion.send_workflow_id == package.send_workflow_id
                )
            )
        ).scalar_one_or_none()
    return SendStatus(
        package_id=package.id,
        workflow_id=package.send_workflow_id,
        status=package.send_status or "idle",  # type: ignore[arg-type]
        error=package.send_error,
        version=version.version if version is not None else None,
        recipient_email=await _recipient(db, package),
        sent_at=version.sent_at if version is not None else None,
    )


def letter_url(package_id: uuid.UUID, version: int) -> str:
    return f"/api/v1/packages/{package_id}/letter.pdf?version={version}"


async def list_versions(db: AsyncSession, package: QuotePackage) -> list[SentVersion]:
    rows = (
        await db.execute(
            select(QuotePackageVersion, OutboxEmail)
            .outerjoin(OutboxEmail, OutboxEmail.id == QuotePackageVersion.outbox_email_id)
            .where(QuotePackageVersion.package_id == package.id)
            .order_by(QuotePackageVersion.version.desc())
        )
    ).all()
    recipient = await _recipient(db, package)
    return [
        SentVersion(
            id=version.id,
            version=version.version,
            sent_at=version.sent_at,
            expires_at=version.expires_at,
            superseded=version.superseded,
            viewed_at=version.viewed_at,
            report_url=report_url(version.report_token),
            letter_url=letter_url(package.id, version.version) if version.letter_key else None,
            outbox_email_id=version.outbox_email_id,
            email_status=outbox.status.value if outbox is not None else None,  # type: ignore[arg-type]
            recipient_email=outbox.to_email if outbox is not None else recipient,
        )
        for version, outbox in rows
    ]


async def letter_pdf(
    db: AsyncSession, package: QuotePackage, version_number: int | None
) -> tuple[bytes, int]:
    """The stored PDF of `version_number`, or of the newest version that has
    one. 404 when there is none."""
    stmt = select(QuotePackageVersion).where(
        QuotePackageVersion.package_id == package.id,
        QuotePackageVersion.letter_key.is_not(None),
    )
    if version_number is not None:
        stmt = stmt.where(QuotePackageVersion.version == version_number)
    version = (
        await db.execute(stmt.order_by(QuotePackageVersion.version.desc()).limit(1))
    ).scalar_one_or_none()
    if version is None or version.letter_key is None:
        raise NotFoundError("No letter has been sent for this package.")
    pdf = await storage.get_object(version.letter_key)
    if pdf is None:
        raise NotFoundError("The letter file is missing.")
    return pdf, version.version
