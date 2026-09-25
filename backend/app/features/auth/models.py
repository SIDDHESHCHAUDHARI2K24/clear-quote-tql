"""`users` (staff) and `borrower_accounts` (portal login) tables.

`borrower_accounts.client_id` references `clients.clients` by table name
(string `ForeignKey`) rather than importing the `Client` model, so this
module and `app.features.clients.models` can each reference the other's
table without a circular Python import — SQLAlchemy resolves string FKs
against `Base.metadata` when mappers are configured, not at import time.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, pg_enum
from app.core.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"))
    full_name: Mapped[str] = mapped_column(String)
    nmls: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BorrowerAccount(Base):
    __tablename__ = "borrower_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), unique=True, index=True
    )
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    # CQ-015: nullable so a pre-existing row (there are none pre-CQ-015, but
    # the columns are nullable per spec.md's migration scope regardless)
    # never blocks the migration; `signup`/`verify_otp` always set both on
    # account creation, so a fully-migrated flow never leaves either null.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
