"""`provider_tax_rates`: seeded mock county property-tax rates."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProviderTaxRate(Base):
    __tablename__ = "provider_tax_rates"
    __table_args__ = (UniqueConstraint("county", "state"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    county: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String(2))
    annual_rate_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    source_name: Mapped[str] = mapped_column(String)
    as_of: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
