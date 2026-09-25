"""`properties` table: subject property (or TBD placeholder) + buy-box."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum


class PropertyAddressStatus(enum.StrEnum):
    SPECIFIC_ADDRESS = "specific_address"
    TBD = "tbd"


class PropertyType(enum.StrEnum):
    SINGLE_FAMILY = "single_family"
    TWO_TO_FOUR_UNIT = "two_to_four_unit"
    CONDO = "condo"
    TOWNHOME = "townhome"


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), unique=True
    )
    address_status: Mapped[PropertyAddressStatus] = mapped_column(
        pg_enum(PropertyAddressStatus, "property_address_status")
    )
    street_address: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip: Mapped[str | None] = mapped_column(String(5), nullable=True)
    county: Mapped[str | None] = mapped_column(String, nullable=True)
    property_type: Mapped[PropertyType] = mapped_column(pg_enum(PropertyType, "property_type"))
    number_of_units: Mapped[int] = mapped_column(Integer, default=1)
    buy_box_states: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    buy_box_metros: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    recommend_matches: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
