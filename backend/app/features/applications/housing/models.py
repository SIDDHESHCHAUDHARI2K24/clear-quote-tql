"""`housing_history` table: 24-month residence history per application."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


class HousingStatus(enum.StrEnum):
    OWN = "own"
    RENT = "rent"
    RENT_FREE = "rent_free"


class HousingHistory(Base):
    __tablename__ = "housing_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    """0 = current residence, 1 = previous, etc."""
    street_address: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String(2))
    zip: Mapped[str] = mapped_column(String(5))
    housing_status: Mapped[HousingStatus] = mapped_column(pg_enum(HousingStatus, "housing_status"))
    residence_years: Mapped[int] = mapped_column(Integer)
    residence_months: Mapped[int] = mapped_column(Integer)
    vom_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
