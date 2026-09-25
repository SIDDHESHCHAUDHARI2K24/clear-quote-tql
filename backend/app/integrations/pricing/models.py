"""`provider_rate_sheet`: seeded mock Optimal Blue rate sheet rows."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


class RateSheetProgram(enum.StrEnum):
    CONVENTIONAL = "conventional"
    DSCR = "dscr"


class ProviderRateSheet(Base):
    __tablename__ = "provider_rate_sheet"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investor_name: Mapped[str] = mapped_column(String)
    product_name: Mapped[str] = mapped_column(String)
    program: Mapped[RateSheetProgram] = mapped_column(
        pg_enum(RateSheetProgram, "rate_sheet_program")
    )
    base_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    base_price: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    min_fico: Mapped[int] = mapped_column(Integer)
    max_ltv: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    dscr_bucket: Mapped[str | None] = mapped_column(String, nullable=True)
    ppp_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    str_only: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_source: Mapped[str | None] = mapped_column(String, nullable=True)
    lock_days: Mapped[int] = mapped_column(Integer)
    fico_adjustment_bps: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    ltv_adjustment_bps: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
