"""`applications` (the loan file header) and `application_parties`
(borrower / co-borrower 1003 profile) tables.

`PartyRole`, `MaritalStatus` and `BusinessVesting` are feature-specific
enums (only `application_parties` uses them), so they live here rather
than in `core/enums.py` per the spec's enum-placement table.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum
from app.core.encryption import EncryptedString
from app.core.enums import ApplicationStatus, LoanPurpose, Occupancy, Strategy


class PartyRole(enum.StrEnum):
    BORROWER = "borrower"
    CO_BORROWER = "co_borrower"


class MaritalStatus(enum.StrEnum):
    MARRIED = "married"
    UNMARRIED = "unmarried"
    SEPARATED = "separated"


class BusinessVesting(enum.StrEnum):
    TITLE_LIEN_IN_LLC = "title_lien_in_llc"
    PERSONAL_NAME = "personal_name"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), index=True
    )
    lo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    los_loan_guid: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status"),
        default=ApplicationStatus.INTAKE,
        index=True,
    )
    occupancy: Mapped[Occupancy] = mapped_column(pg_enum(Occupancy, "occupancy"))
    strategy: Mapped[Strategy | None] = mapped_column(pg_enum(Strategy, "strategy"), nullable=True)
    program: Mapped[str | None] = mapped_column(String, nullable=True)
    purpose: Mapped[LoanPurpose] = mapped_column(
        pg_enum(LoanPurpose, "loan_purpose"), default=LoanPurpose.PURCHASE
    )
    requested_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Denormalized from `properties`/`housing_history` for the
    # applications-list filter, per spec.
    subject_state: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ApplicationParty(Base):
    __tablename__ = "application_parties"
    __table_args__ = (UniqueConstraint("application_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[PartyRole] = mapped_column(pg_enum(PartyRole, "party_role"))
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String)
    ssn_encrypted: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    marital_status: Mapped[MaritalStatus | None] = mapped_column(
        pg_enum(MaritalStatus, "marital_status"), nullable=True
    )
    dependents_count: Mapped[int] = mapped_column(Integer, default=0)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    cell_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    home_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    work_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    business_vesting: Mapped[BusinessVesting | None] = mapped_column(
        pg_enum(BusinessVesting, "business_vesting"), nullable=True
    )
    llc_entity_name: Mapped[str | None] = mapped_column(String, nullable=True)
    no_co_applicant_check: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
