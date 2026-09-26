"""`field_values` and `flags` tables.

CQ-012 owns the rule logic that populates these; this item defines the
shape only.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum
from app.core.enums import ApplicationTab, FieldSource, FlagSeverity


class FieldValue(Base):
    __tablename__ = "field_values"
    __table_args__ = (UniqueConstraint("application_id", "field_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    field_key: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    source: Mapped[FieldSource] = mapped_column(pg_enum(FieldSource, "field_source"))
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    """e.g. a `provider_*` row id."""
    overridden_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        Index("ix_flags_application_id_resolved_at", "application_id", "resolved_at"),
        # CQ-028a review M1: at most one open flag per (application, field, rule).
        Index(
            "uq_flags_open_application_field_rule",
            "application_id",
            "field_key",
            "rule",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    tab: Mapped[ApplicationTab] = mapped_column(pg_enum(ApplicationTab, "application_tab"))
    field_key: Mapped[str] = mapped_column(String)
    rule: Mapped[str] = mapped_column(String)
    """Rule id, e.g. `housing_history_24mo` or `ob_required_field`."""
    severity: Mapped[FlagSeverity] = mapped_column(pg_enum(FlagSeverity, "flag_severity"))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    """P5/P6 foundation (E8): human-readable text shown next to the field,
    set by `verification.service.write_flag` (rule text from `rules.py`)."""
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
