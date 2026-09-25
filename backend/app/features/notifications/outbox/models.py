"""`outbox_emails` table: the always-on in-app demo outbox."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


class EmailStatus(enum.StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class OutboxEmail(Base):
    __tablename__ = "outbox_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    to_email: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    html: Mapped[str] = mapped_column(Text)
    attachment_keys: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[EmailStatus] = mapped_column(
        pg_enum(EmailStatus, "email_status"), default=EmailStatus.QUEUED
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
