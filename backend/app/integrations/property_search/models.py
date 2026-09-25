"""`provider_listings`: seeded mock property-search listings."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum
from app.features.applications.property.models import PropertyType


class DealGrade(enum.StrEnum):
    GREAT_BUY = "great_buy"
    GOOD_BUY = "good_buy"


class ProviderListing(Base):
    __tablename__ = "provider_listings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String(2))
    zip: Mapped[str] = mapped_column(String(5))
    county: Mapped[str] = mapped_column(String)
    """CQ-023: needed to call `MockTaxClient.get_tax_rate(state, county)` per
    listing (matches `MockTaxClient`'s own signature -- county rates are keyed
    `(state, county)`, not `(state, zip)`)."""
    metro: Mapped[str] = mapped_column(String)
    list_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    beds: Mapped[int] = mapped_column(Integer)
    baths: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    sqft: Mapped[int] = mapped_column(Integer)
    property_type: Mapped[PropertyType] = mapped_column(pg_enum(PropertyType, "property_type"))
    image_url: Mapped[str] = mapped_column(String)
    deal_grade: Mapped[DealGrade] = mapped_column(pg_enum(DealGrade, "deal_grade"))
    tagline: Mapped[str | None] = mapped_column(String, nullable=True)
    str_permitted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    """CQ-023: STR strategy fit filters matches to `str_permitted` listings
    only (spec.md); LTR/primary never filter on this."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
