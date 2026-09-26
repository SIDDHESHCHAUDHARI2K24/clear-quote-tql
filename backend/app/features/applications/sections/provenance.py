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
- `auto:{field_key}` -- written by CQ-012's `phone_copy` auto-fix
  (`verification.service.mark_auto_copied`) when it fills the primary home
  phone from the cell phone; read here to keep that phone following the
  cell phone (AC3).

None of these helpers commit.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.encryption import _fernet
from app.core.enums import FieldSource
from app.features.applications.verification.models import FieldValue
from app.features.applications.verification.service import AUTO_PREFIX, auto_marker_key

ORIG_PREFIX = "orig:"
ROW_PREFIX = "row:"


def seal(value: Any) -> Any:
    """Encrypts a sensitive original (SSN, DOB) before it is stored in the
    plain JSONB `field_values.value` (same Fernet key as `EncryptedString`)."""
    if value is None:
        return None
    token = _fernet().encrypt(json.dumps(value).encode("utf-8")).decode("ascii")
    return {"enc": token}


def unseal(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("enc"), str):
        return json.loads(_fernet().decrypt(value["enc"].encode("ascii")).decode("utf-8"))
    return value


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


async def has_auto_marker(db: AsyncSession, application_id: uuid.UUID, field_key: str) -> bool:
    """True when a rule auto-copied this field (`auto:` marker, see
    `verification.service.mark_auto_copied`)."""
    marker = (
        await db.execute(
            select(FieldValue.id).where(
                FieldValue.application_id == application_id,
                FieldValue.field_key == auto_marker_key(field_key),
            )
        )
    ).scalar_one_or_none()
    return marker is not None


async def load_auto_markers(db: AsyncSession, application_id: uuid.UUID) -> set[str]:
    """Field keys (prefix stripped) a rule auto-copied."""
    keys = (
        (
            await db.execute(
                select(FieldValue.field_key).where(
                    FieldValue.application_id == application_id,
                    FieldValue.field_key.startswith(AUTO_PREFIX),
                )
            )
        )
        .scalars()
        .all()
    )
    return {key[len(AUTO_PREFIX) :] for key in keys}


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
    if existing is None:
        # Idempotent insert (review M1): the router's application lock already
        # serialises edits; ON CONFLICT is the backstop, so a concurrent first
        # edit keeps the row the other request wrote instead of failing.
        await db.execute(
            insert(FieldValue)
            .values(
                id=uuid.uuid4(),
                application_id=application_id,
                field_key=f"{ORIG_PREFIX}{field_key}",
                value=original_value,
                source=FieldSource.LO_OVERRIDE,
                source_ref=original_source.value,
            )
            .on_conflict_do_nothing(index_elements=["application_id", "field_key"])
        )
        existing = await get_override(db, application_id, field_key)
        assert existing is not None
    existing.overridden_by = user_id
    existing.overridden_at = now()
    await db.flush()
    return existing


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
