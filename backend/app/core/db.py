"""Async SQLAlchemy session plumbing shared by every feature.

No tables are declared here — CQ-007 adds real models under each feature's
`models.py`, all importing `Base` (and `pg_enum`) from this module.
"""

import enum
from collections.abc import AsyncIterator

from sqlalchemy import Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def pg_enum[E: enum.Enum](enum_cls: type[E], name: str) -> SAEnum:
    """A native Postgres enum column type storing each member's `.value`.

    Plain `sqlalchemy.Enum(SomeEnum, name=...)` stores each member's
    `.name` (e.g. `"LO"`) by default, not its `.value` (`"lo"`) — every
    enum in `core/enums.py` and feature `models.py` files is documented as
    lower_snake_case values, so every enum column uses this helper instead
    of `sa.Enum(...)` directly.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda obj: [member.value for member in obj],
    )


engine = create_async_engine(get_settings().database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
