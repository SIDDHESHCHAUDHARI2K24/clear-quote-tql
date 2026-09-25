"""`integration_calls`.

**Decision** (spec): not named in system-design.md's Data model table;
added because CQ-009's adapter-call log and CQ-029's Integration panel need
somewhere to read "last call, latency, result" from.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IntegrationCall(Base):
    __tablename__ = "integration_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    adapter: Mapped[str] = mapped_column(String)
    request_summary: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    success: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True, index=True
    )
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
