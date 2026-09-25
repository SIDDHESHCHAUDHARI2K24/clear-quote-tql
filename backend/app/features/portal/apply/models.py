"""`application_drafts` table (P5/P6 foundation, E1; CQ-032 owns the
autosave/validate/submit endpoints).

One *open* draft per borrower: the partial unique index
`uq_application_drafts_open_per_borrower` covers `borrower_account_id`
only where `submitted_application_id IS NULL`, so a borrower can keep any
number of submitted drafts but only one in progress.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ApplicationDraft(Base):
    __tablename__ = "application_drafts"
    __table_args__ = (
        Index(
            "uq_application_drafts_open_per_borrower",
            "borrower_account_id",
            unique=True,
            postgresql_where=text("submitted_application_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    borrower_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("borrower_accounts.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    """Per-tab dict, e.g. `{"you": {...}, "property": {...}}`."""
    current_tab: Mapped[str] = mapped_column(String, default="you", server_default="you")
    submitted_application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    """Set once on submit; `NULL` means the draft is still open."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
