"""`provider_los_records`: seeded mock Encompass LOS data.

Read-only from the mock adapter's point of view (CQ-009 reads via
`SELECT`; CQ-010 writes seed rows).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProviderLosRecord(Base):
    __tablename__ = "provider_los_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_number: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    """Full mocked 1003 record; field names from the data field catalog."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
