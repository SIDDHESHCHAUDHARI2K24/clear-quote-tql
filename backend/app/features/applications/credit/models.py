"""`liabilities` table.

`total_monthly_liabilities` and `representative_fico`/`credit_score_bracket`
are intentionally NOT stored columns here — per spec they are `field_values`
entries (FICO/bracket sourced from `CreditClient`; the liabilities total is
`SUM(liabilities.monthly_payment)`), so a re-import never leaves a stale
cached total.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Liability(Base):
    __tablename__ = "liabilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    creditor_name: Mapped[str] = mapped_column(String)
    account_type: Mapped[str] = mapped_column(String)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
