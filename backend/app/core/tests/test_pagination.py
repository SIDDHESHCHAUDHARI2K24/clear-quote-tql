"""`core/pagination` (P5/P6 foundation, E4)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.pagination import Page, clamp_page, clamp_page_size, paginate
from app.features.auth.models import User

_TAG = "pagination-test"


async def _seed_users(db: AsyncSession, count: int) -> None:
    for i in range(count):
        db.add(
            User(
                email=f"{_TAG}-{i:03d}-{uuid.uuid4().hex[:6]}@clearquote.test",
                password_hash="x",
                role=UserRole.LO,
                full_name=f"{_TAG} {i:03d}",
            )
        )
    await db.flush()


def _stmt():  # type: ignore[no-untyped-def]
    return select(User).where(User.full_name.like(f"{_TAG}%")).order_by(User.full_name, User.id)


async def test_paginate_returns_page_slice_and_total(db_session: AsyncSession) -> None:
    await _seed_users(db_session, 30)

    first = await paginate(db_session, _stmt(), page=1, page_size=25)
    second = await paginate(db_session, _stmt(), page=2, page_size=25)

    assert first.total == 30 and second.total == 30
    assert [u.full_name for u in first.items] == [f"{_TAG} {i:03d}" for i in range(25)]
    assert [u.full_name for u in second.items] == [f"{_TAG} {i:03d}" for i in range(25, 30)]
    assert (first.page, first.page_size) == (1, 25)
    assert (second.page, second.page_size) == (2, 25)


async def test_paginate_beyond_last_page_is_empty(db_session: AsyncSession) -> None:
    await _seed_users(db_session, 3)
    result = await paginate(db_session, _stmt(), page=5, page_size=10)
    assert result.items == []
    assert result.total == 3


async def test_paginate_multi_column_select_returns_rows(db_session: AsyncSession) -> None:
    await _seed_users(db_session, 2)
    stmt = (
        select(User.id, User.full_name)
        .where(User.full_name.like(f"{_TAG}%"))
        .order_by(User.full_name)
    )
    result = await paginate(db_session, stmt, page=1, page_size=10)
    assert [row.full_name for row in result.items] == [f"{_TAG} 000", f"{_TAG} 001"]


async def test_paginate_clamps_inputs(db_session: AsyncSession) -> None:
    await _seed_users(db_session, 2)
    result = await paginate(db_session, _stmt(), page=0, page_size=500)
    assert result.page == 1
    assert result.page_size == 100


@pytest.mark.parametrize(
    ("given", "expected"), [(None, 25), (0, 1), (-3, 1), (1, 1), (25, 25), (100, 100), (101, 100)]
)
def test_clamp_page_size(given: int | None, expected: int) -> None:
    assert clamp_page_size(given) == expected


@pytest.mark.parametrize(("given", "expected"), [(None, 1), (0, 1), (-1, 1), (3, 3)])
def test_clamp_page(given: int | None, expected: int) -> None:
    assert clamp_page(given) == expected


def test_page_is_a_generic_pydantic_model() -> None:
    class Row(BaseModel):
        name: str

    page = Page[Row](items=[Row(name="a")], total=1, page=1, page_size=25)
    assert page.model_dump() == {
        "items": [{"name": "a"}],
        "total": 1,
        "page": 1,
        "page_size": 25,
    }
    assert Page[Row].model_json_schema()["properties"]["items"]["items"]["$ref"].endswith("Row")
