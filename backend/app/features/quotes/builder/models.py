"""`quotes` table: one priced option within a scenario."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, false, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    investor: Mapped[str] = mapped_column(String)
    product: Mapped[str] = mapped_column(String)
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    points: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    lock_days: Mapped[int] = mapped_column(Integer)
    computed: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    """Full `quote_engine` output."""
    label: Mapped[str] = mapped_column(String)
    """`Par` / `Buydown` / `Manual`."""
    priced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    """P3/P4 foundation: CQ-017 sets this when a field-value override or
    revert (`pricing/enrichment`) changes an input this quote was priced
    from, so the pricing panel can flag it as needing a reprice (CQ-018)."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
