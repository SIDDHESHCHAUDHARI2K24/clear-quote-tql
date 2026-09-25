"""`scenarios` table: one per Add/Edit scenario action.

`dscr_bucket` stores one of CQ-008's `DSCRBucket` member *names* (e.g.
`"BELOW_1_00"`) as plain text — this item doesn't depend on CQ-008's
`quote_engine` module, so it's a `String`, not that enum.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    inputs: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    config_snapshot: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    """The `settings` snapshot used, so old quotes never change when defaults do."""
    dscr_bucket: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
