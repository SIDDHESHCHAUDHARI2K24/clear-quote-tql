"""`consents` table: hard-pull authorization requests and decisions.

P5/P6 foundation (phase-p5-p6-plan.md E1/E11): a row now starts as a
`pending` *request* (CQ-028's "Request hard pull" writes `requested_by`,
`requested_at`, `expires_at`), and CQ-033 records the borrower's decision
on it (`accepted` with `typed_name`, `ip`, `user_agent`, `text_version`,
`text_hash`, `at`; or `declined` with `decline_reason`). Rows written
before the foundation migration are backfilled as `accepted`. Decision
fields are written once; there is still no `updated_at`.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


class ConsentType(enum.StrEnum):
    HARD_PULL = "hard_pull"
    APPLICATION = "application"
    """CQ-032: the apply wizard's tab-4 consent (soft-pull authorization,
    contact consent, terms), recorded `accepted` at submit."""


class ConsentStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[ConsentType] = mapped_column(pg_enum(ConsentType, "consent_type"))
    status: Mapped[ConsentStatus] = mapped_column(
        pg_enum(ConsentStatus, "consent_status"),
        default=ConsentStatus.PENDING,
        server_default=ConsentStatus.PENDING.value,
    )
    """ORM default `pending` (new requests); the column's server default
    matches. The migration backfills every pre-existing (pre-migration) row
    to `accepted` via `ADD COLUMN ... DEFAULT 'accepted'`, then switches the
    server default to `pending` -- existing row values are unaffected by the
    switch, but any insert that skips the ORM default (e.g. raw SQL) still
    gets a pending request."""
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    text_version: Mapped[str | None] = mapped_column(String, nullable=True)
    text_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    typed_name: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """When the consent was given (accepted); `None` while pending."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
