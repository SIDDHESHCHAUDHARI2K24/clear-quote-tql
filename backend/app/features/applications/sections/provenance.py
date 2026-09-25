"""Field provenance for LO edits of 1003 data (plan.md Decision #3).

The domain tables (`application_parties`, `housing_history`, ...) always
hold the *current* value; the rule engine and every other reader keep
reading them. Provenance lives in `field_values` under two reserved key
prefixes (both contain `:`, which no catalog key does):

- `orig:{field_key}` -- written on the first LO edit of an imported field.
  `value` is the ORIGINAL value (JSON), `source_ref` the original source,
  `source = lo_override`, `overridden_by/at` the last editor. Revert writes
  `value` back to the domain column and deletes the row.
- `row:{collection}:{row_id}` -- marks a row the LO added by hand
  (`source = lo_entry`), e.g. a manual liability that "Import liabilities"
  must keep.

None of these helpers commit.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.enums import FieldSource
from app.features.applications.verification.models import FieldValue

ORIG_PREFIX = "orig:"
ROW_PREFIX = "row:"


def row_marker_key(collection: str, row_id: uuid.UUID) -> str:
    return f"{ROW_PREFIX}{collection}:{row_id}"


async def load_overrides(db: AsyncSession, application_id: uuid.UUID) -> dict[str, FieldValue]:
    """`field_key` (prefix stripped) -> its `orig:` provenance row."""
    rows = (
        (
            await db.execute(
                select(FieldValue).where(
                    FieldValue.application_id == application_id,
                    FieldValue.field_key.startswith(ORIG_PREFIX),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.field_key[len(ORIG_PREFIX) :]: row for row in rows}


async def load_manual_rows(db: AsyncSession, application_id: uuid.UUID) -> set[str]:
    """The `row:` marker keys (prefix kept) for this application."""
    keys = (
        (
            await db.execute(
                select(FieldValue.field_key).where(
                    FieldValue.application_id == application_id,
                    FieldValue.field_key.startswith(ROW_PREFIX),
                )
            )
        )
        .scalars()
        .all()
    )
    return set(keys)


async def get_override(
    db: AsyncSession, application_id: uuid.UUID, field_key: str
) -> FieldValue | None:
    return (
        await db.execute(
            select(FieldValue).where(
                FieldValue.application_id == application_id,
                FieldValue.field_key == f"{ORIG_PREFIX}{field_key}",
            )
        )
    ).scalar_one_or_none()


async def record_override(
    db: AsyncSession,
    application_id: uuid.UUID,
    field_key: str,
    *,
    original_value: Any,
    original_source: FieldSource,
    user_id: uuid.UUID,
) -> FieldValue:
    """Creates the `orig:` row on the first edit; later edits only refresh
    who/when, so the original value is kept."""
    existing = await get_override(db, application_id, field_key)
    if existing is not None:
        existing.overridden_by = user_id
        existing.overridden_at = now()
        await db.flush()
        return existing
    row = FieldValue(
        application_id=application_id,
        field_key=f"{ORIG_PREFIX}{field_key}",
        value=original_value,
        source=FieldSource.LO_OVERRIDE,
        source_ref=original_source.value,
        overridden_by=user_id,
        overridden_at=now(),
    )
    db.add(row)
    await db.flush()
    return row


async def mark_manual_row(
    db: AsyncSession, application_id: uuid.UUID, collection: str, row_id: uuid.UUID
) -> None:
    db.add(
        FieldValue(
            application_id=application_id,
            field_key=row_marker_key(collection, row_id),
            value=FieldSource.LO_ENTRY.value,
            source=FieldSource.LO_ENTRY,
        )
    )
    await db.flush()


async def delete_row_provenance(
    db: AsyncSession, application_id: uuid.UUID, collection: str, row_id: uuid.UUID
) -> None:
    """Drops a row's marker and every `orig:` override of its fields (used
    when "Import liabilities" replaces an imported row)."""
    await db.execute(
        delete(FieldValue).where(
            FieldValue.application_id == application_id,
            FieldValue.field_key.in_([row_marker_key(collection, row_id)])
            | FieldValue.field_key.startswith(f"{ORIG_PREFIX}{collection}.{row_id}."),
        )
    )
