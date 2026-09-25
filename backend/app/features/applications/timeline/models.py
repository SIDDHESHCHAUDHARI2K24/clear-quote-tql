"""`activity_events` table: append-only application timeline + CRM log."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ActivityEvent(Base):
    """Append-only: no `updated_at` (matches the spec's convention for
    append-only tables — rows are never edited after creation)."""

    __tablename__ = "activity_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    actor: Mapped[str] = mapped_column(String)
    """A user id (as string) or the literal `"system"`."""
    type: Mapped[str] = mapped_column(String)
    """e.g. `stage.completed`, `email.sent`, `flag.raised`."""
    payload: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
