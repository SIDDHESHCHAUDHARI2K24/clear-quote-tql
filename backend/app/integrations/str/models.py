"""`provider_str_revenue`: seeded mock AirDNA short-term-rental comps."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProviderStrRevenue(Base):
    __tablename__ = "provider_str_revenue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zip: Mapped[str] = mapped_column(String(5))
    beds: Mapped[int] = mapped_column(Integer)
    annual_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    occupancy_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    adr: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    comps_count: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
