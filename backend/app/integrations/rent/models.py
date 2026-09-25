"""`provider_rents`: seeded mock RentCast long-term-rent comps."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProviderRent(Base):
    __tablename__ = "provider_rents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zip: Mapped[str] = mapped_column(String(5))
    beds: Mapped[int] = mapped_column(Integer)
    market_rent: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rent_low: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rent_high: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    comps_count: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
