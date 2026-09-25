"""Row edits for `housing_history`, `parties` and `liabilities` (spec
"Row edits"). Adds write a `row:` provenance marker (the row is the LO's,
not imported) and a `row.added` event; edits go through the same per-field
engine as `PUT /fields` (`fields.apply_field_edit`), so each changed column
gets its own override + event. Nothing here commits.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.sections import events, provenance
from app.features.applications.sections.fields import (
    apply_field_edit,
    party_field_key,
    row_field_key,
    to_json,
)
from app.features.applications.sections.schemas import (
    HousingCreate,
    LiabilityCreate,
    PartyCreate,
)


def _row_added(
    db: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    collection: str,
    row_id: uuid.UUID,
    message: str,
) -> None:
    events.add_event(
        db,
        application_id,
        actor=events.actor_for(user_id),
        type=events.ROW_ADDED,
        payload={"collection": collection, "row_id": str(row_id), "message": message},
    )


async def add_housing(
    db: AsyncSession, application: Application, body: HousingCreate, user_id: uuid.UUID
) -> HousingHistory:
    max_sequence = (
        await db.execute(
            select(func.max(HousingHistory.sequence)).where(
                HousingHistory.application_id == application.id
            )
        )
    ).scalar_one_or_none()
    row = HousingHistory(
        application_id=application.id,
        sequence=0 if max_sequence is None else max_sequence + 1,
        street_address=body.street_address.strip(),
        city=body.city.strip(),
        state=body.state.upper(),
        zip=body.zip,
        housing_status=body.housing_status,
        residence_years=body.residence_years,
        residence_months=body.residence_months,
        vom_completed=body.vom_completed,
    )
    db.add(row)
    await db.flush()
    await provenance.mark_manual_row(db, application.id, "housing_history", row.id)
    months = body.residence_years * 12 + body.residence_months
    _row_added(
        db,
        application.id,
        user_id,
        "housing_history",
        row.id,
        f"Added prior address {row.street_address} ({months} months)",
    )
    return row


async def add_co_borrower(
    db: AsyncSession, application: Application, body: PartyCreate, user_id: uuid.UUID
) -> ApplicationParty:
    parties = (
        (
            await db.execute(
                select(ApplicationParty).where(ApplicationParty.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    if any(p.role is PartyRole.CO_BORROWER for p in parties):
        raise ConflictError("This application already has a co-borrower.")
    party = ApplicationParty(
        application_id=application.id,
        role=PartyRole.CO_BORROWER,
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        ssn_encrypted=body.ssn.replace("-", "").replace(" ", "") if body.ssn else None,
        dob=body.dob,
        email=body.email,
        cell_phone=body.cell_phone,
        home_phone=body.home_phone,
        work_phone=body.work_phone,
    )
    db.add(party)
    for primary in parties:
        if primary.role is PartyRole.BORROWER:
            primary.no_co_applicant_check = False
    await db.flush()
    await provenance.mark_manual_row(db, application.id, "parties", party.id)
    _row_added(
        db,
        application.id,
        user_id,
        "parties",
        party.id,
        f"Added co-borrower {party.first_name} {party.last_name}",
    )
    return party


async def add_liability(
    db: AsyncSession, application: Application, body: LiabilityCreate, user_id: uuid.UUID
) -> Liability:
    row = Liability(
        application_id=application.id,
        creditor_name=body.creditor_name.strip(),
        account_type=body.account_type.strip(),
        monthly_payment=body.monthly_payment,
        balance=body.balance,
    )
    db.add(row)
    await db.flush()
    await provenance.mark_manual_row(db, application.id, "liabilities", row.id)
    _row_added(
        db,
        application.id,
        user_id,
        "liabilities",
        row.id,
        f"Added liability {row.creditor_name} (${row.monthly_payment}/mo)",
    )
    return row


async def patch_row(
    db: AsyncSession,
    application: Application,
    collection: str,
    row_id: uuid.UUID,
    changes: dict[str, Any],
    user_id: uuid.UUID,
) -> None:
    for column, value in changes.items():
        await apply_field_edit(
            db, application, row_field_key(collection, row_id, column), to_json(value), user_id
        )


async def patch_party(
    db: AsyncSession,
    application: Application,
    party_id: uuid.UUID,
    changes: dict[str, Any],
    user_id: uuid.UUID,
) -> None:
    party = await db.get(ApplicationParty, party_id)
    if party is None or party.application_id != application.id:
        raise NotFoundError(f"No party {party_id} on this application.")
    for column, value in changes.items():
        await apply_field_edit(
            db, application, party_field_key(party.role, column), to_json(value), user_id
        )
