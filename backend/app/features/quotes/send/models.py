"""`quote_packages` table: what the borrower sees when a quote is sent, and
`quote_package_versions`: the frozen snapshots CQ-020 writes each time a
package is actually sent (D2, docs/backlog/phase-p3-p4-foundation.md) --
`quote_packages` itself stays the draft/working package."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

# CQ-020: `quote_package_versions.outbox_email_id` is a foreign key to
# `outbox_emails`. Importing that model here registers its table wherever
# this module is loaded on its own (e.g. `backend/scripts/
# freeze_sent_version.py`), otherwise the first flush raises
# NoReferencedTableError.
import app.features.notifications.outbox.models  # noqa: F401
from app.core.db import Base, pg_enum


class SendStatus(enum.StrEnum):
    """CQ-020 (plan.md Decision 7): `quote_packages.send_status`, written by
    the `SendQuotePackage` activities and read by `GET /send-status`.
    Stored as a plain string column (no Postgres enum) -- `None` means the
    package was never sent through the workflow ("idle" in the API)."""

    QUEUED = "queued"
    RENDERING = "rendering"
    EMAILING = "emailing"
    DONE = "done"
    FAILED = "failed"


IN_FLIGHT_SEND_STATUSES = frozenset(
    {SendStatus.QUEUED.value, SendStatus.RENDERING.value, SendStatus.EMAILING.value}
)


class BorrowerAction(enum.StrEnum):
    OPTION_SELECTED = "option_selected"
    INQUIRY = "inquiry"


class QuotePackage(Base):
    __tablename__ = "quote_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), index=True
    )
    quote_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    recommended_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id"), nullable=True, index=True
    )
    lo_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    """CQ-019: the "What we recommend" sentence, pre-drafted by the server
    from the recommended quote's scenario and re-drafted whenever the
    recommendation changes. `freeze_package_version` uses it, so the sent
    report says exactly what the Send tab preview said."""
    letter_key: Mapped[str | None] = mapped_column(String, nullable=True)
    """MinIO key."""
    report_token: Mapped[str] = mapped_column(String, unique=True, index=True)
    """The magic-link token."""
    lo_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    """Set once `update_package` (`PUT`) has ever run for this draft.
    Distinguishes an unsent draft the LO deliberately emptied (`quote_ids:
    []`, `lo_edited=True`) from one that's empty only because it predates
    any priced quote (`lo_edited=False`) -- only the latter gets the
    default selection re-applied on the next `GET` (post-merge review,
    code-review follow-up on M5). A timestamp comparison (`created_at ==
    updated_at`) was tried first and dropped: Postgres's `now()` is
    transaction-start time, so it's unreliable whenever a create and a
    later write land in the same transaction (as they do under this
    codebase's `db_session` test fixture)."""
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    borrower_action: Mapped[BorrowerAction | None] = mapped_column(
        pg_enum(BorrowerAction, "borrower_action"), nullable=True
    )
    send_workflow_id: Mapped[str | None] = mapped_column(String, nullable=True)
    """CQ-020: the newest `SendQuotePackage` workflow started for this
    package. Activities only write `send_status` while this is their own id,
    so a stale run can't overwrite a newer one's progress."""
    send_status: Mapped[str | None] = mapped_column(String, nullable=True)
    """CQ-020: a `SendStatus` value, `None` until the first send."""
    send_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """CQ-020: why the last send failed (`send_status == "failed"`)."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QuotePackageVersion(Base):
    """One frozen, sent snapshot of a `QuotePackage` (P3/P4 foundation, D1/D2).

    CQ-020's send workflow writes a new row here each time a package is
    sent (never updates an old one); CQ-022's portal report and CQ-024's
    borrower actions read the row selected by `report_token`. The token --
    not `quote_packages.report_token`, which this migration leaves alone --
    is the one a sent email links to; it only *selects* a version and is
    never itself a credential (the borrower session gates access, H2).
    """

    __tablename__ = "quote_package_versions"
    __table_args__ = (UniqueConstraint("package_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote_packages.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    """1-based, increasing per `package_id` (unique together, above)."""
    snapshot: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    """The frozen `ReportViewModel` (CQ-021) as of send time."""
    letter_key: Mapped[str | None] = mapped_column(String, nullable=True)
    """MinIO key of the rendered letter PDF."""
    report_token: Mapped[str] = mapped_column(String, unique=True, index=True)
    """Opaque link token (`/report/{token}`); not a credential (H2) -- the
    borrower session, not the token, is what gates access."""
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    """`sent_at` + 21 days (H2)."""
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Set on the first successful borrower load (CQ-022 AC2); later loads
    never overwrite it."""
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    """True once a newer version of the same package has been sent."""
    borrower_action: Mapped[dict | list | str | float | bool | None] = mapped_column(
        JSONB, nullable=True
    )
    """CQ-024: move_forward / ask_other / ask_updated, null until acted on."""
    send_workflow_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    """CQ-020 (plan.md Decision 8): the `SendQuotePackage` workflow that
    froze this version -- the Freeze activity's idempotency key. `None` for
    versions frozen outside the workflow (seed, test factories)."""
    outbox_email_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outbox_emails.id"), nullable=True, index=True
    )
    """CQ-020: the borrower email sent for this version (the Email
    activity's idempotency key; the LO's "Open in Outbox" link)."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
