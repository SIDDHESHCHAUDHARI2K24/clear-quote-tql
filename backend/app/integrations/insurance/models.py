"""`provider_insurance_factors`: seeded mock Steadily state insurance rates."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProviderInsuranceFactor(Base):
    __tablename__ = "provider_insurance_factors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(2), unique=True)
    annual_rate_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.50"))
    source_name: Mapped[str] = mapped_column(String, default="Steadily")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
