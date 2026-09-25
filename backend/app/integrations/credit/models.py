"""`provider_credit_reports`: seeded mock credit bureau pull results."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


class CreditPullType(enum.StrEnum):
    SOFT_PULL = "soft_pull"
    HARD_PULL = "hard_pull"


class ProviderCreditReport(Base):
    __tablename__ = "provider_credit_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_number: Mapped[str] = mapped_column(String)
    pull_type: Mapped[CreditPullType] = mapped_column(pg_enum(CreditPullType, "credit_pull_type"))
    experian_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equifax_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transunion_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    middle_score: Mapped[int] = mapped_column(Integer)
    tradelines: Mapped[dict | list | str | float | bool | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
