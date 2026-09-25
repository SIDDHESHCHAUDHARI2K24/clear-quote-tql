"""Shared page/offset pagination (P5/P6 foundation, E4).

Every P5/P6 list endpoint (CQ-026 clients, CQ-027 applications, CQ-029
activity/outbox) returns a `Page[RowSchema]` and builds it with
`paginate(db, stmt, page, page_size)`:

    result = await paginate(db, stmt, page, page_size)
    return Page[ApplicationRow](
        items=[ApplicationRow.model_validate(row) for row in result.items],
        total=result.total, page=result.page, page_size=result.page_size,
    )

`stmt` must already carry its `ORDER BY` (a stable one: add the primary
key as the last tie-breaker) — pagination never reorders.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


def clamp_page_size(page_size: int | None) -> int:
    """`None` -> 25; otherwise clamped to 1..100."""
    if page_size is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(MAX_PAGE_SIZE, page_size))


def clamp_page(page: int | None) -> int:
    """`None` or anything below 1 -> 1 (pages are 1-based)."""
    return max(1, page or 1)


async def paginate(
    db: AsyncSession,
    stmt: Select[Any],
    page: int | None = 1,
    page_size: int | None = DEFAULT_PAGE_SIZE,
) -> Page[Any]:
    """Runs `stmt` for one page plus a `COUNT(*)` over the unpaged query.

    `items` are the ORM entities when `stmt` selects exactly one entity or
    column (`select(Application)`), else `Row` tuples (`select(A.id,
    A.status)`), so callers map them to their schema.
    """
    page = clamp_page(page)
    page_size = clamp_page_size(page_size)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    paged = stmt.limit(page_size).offset((page - 1) * page_size)
    result = await db.execute(paged)
    items: list[Any]
    # `column_descriptions` has one entry per selected entity/column
    # (`selected_columns` would expand an entity into all its columns).
    if len(stmt.column_descriptions) == 1:
        items = list(result.scalars().all())
    else:
        items = list(result.all())

    return Page[Any](items=items, total=total, page=page, page_size=page_size)
