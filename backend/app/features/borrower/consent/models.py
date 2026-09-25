"""`consents` table: hard-pull authorization capture (append-only)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


class ConsentType(enum.StrEnum):
    HARD_PULL = "hard_pull"


class Consent(Base):
    """Append-only: no `updated_at`."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[ConsentType] = mapped_column(pg_enum(ConsentType, "consent_type"))
    text_hash: Mapped[str] = mapped_column(String)
    ip: Mapped[str] = mapped_column(String)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
