"""`quote_packages` table: what the borrower sees when a quote is sent."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


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
    letter_key: Mapped[str | None] = mapped_column(String, nullable=True)
    """MinIO key."""
    report_token: Mapped[str] = mapped_column(String, unique=True, index=True)
    """The magic-link token."""
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    borrower_action: Mapped[BorrowerAction | None] = mapped_column(
        pg_enum(BorrowerAction, "borrower_action"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
