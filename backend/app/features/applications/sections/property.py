"""Property-tab actions (spec "Property actions"; plan.md #16-#18) and
document receipt (plan.md #23). Nothing here commits.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.errors import NotFoundError, ValidationAppError
from app.features.applications.assets.models import Document
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.sections import events, provenance
from app.features.applications.sections.schemas import PropertyPatch
from app.features.reference.service import (
    county_for_zip,
    metros_for_states,
    normalize_states,
)


async def update_property(
    db: AsyncSession, application: Application, body: PropertyPatch, user_id: uuid.UUID
) -> list[str]:
    """Applies the patch; returns the list of changes (for the event)."""
    prop = (
        await db.execute(select(Property).where(Property.application_id == application.id))
    ).scalar_one_or_none()
    if prop is None:
        raise NotFoundError("This application has no property record.")
    if body.address is not None and body.tbd:
        raise ValidationAppError("Send either an address or tbd=true, not both.")
    if body.tbd is False and body.address is None:
        raise ValidationAppError("Enter an address to take the property off TBD.")

    changes: list[str] = []
    if body.address is not None:
        address = body.address
        state = address.state.upper()
        county = await county_for_zip(db, address.zip) or address.county
        prop.address_status = PropertyAddressStatus.SPECIFIC_ADDRESS
        prop.street_address = address.street_address.strip()
        prop.city = address.city.strip()
        prop.state = state
        prop.zip = address.zip
        prop.county = county
        prop.recommend_matches = False
        application.subject_state = state
        changes.append(f"address set to {prop.street_address}, {prop.city}, {state} {prop.zip}")
        changes.append("recommend matches off")
    elif body.tbd:
        prop.address_status = PropertyAddressStatus.TBD
        prop.street_address = None
        prop.recommend_matches = True
        changes.append("property marked TBD")
        changes.append("recommend matches on")

    if body.recommend_matches is not None and body.recommend_matches != prop.recommend_matches:
        prop.recommend_matches = body.recommend_matches
        changes.append(f"recommend matches {'on' if body.recommend_matches else 'off'}")

    states_changed = False
    if body.buy_box_states is not None:
        states = normalize_states(body.buy_box_states)
        states_changed = states != list(prop.buy_box_states or [])
        prop.buy_box_states = states
        changes.append(f"buy-box states: {', '.join(states) or 'none'}")

    if body.buy_box_metros is not None or states_changed:
        allowed_by_state = await metros_for_states(db, list(prop.buy_box_states or []))
        allowed = {metro for metros in allowed_by_state.values() for metro in metros}
        if body.buy_box_metros is not None:
            metros: list[str] = []
            for raw in body.buy_box_metros:
                metro = raw.strip()
                if metro not in allowed:
                    raise ValidationAppError(
                        f"{metro!r} is not a metro in the selected states "
                        f"({', '.join(prop.buy_box_states or []) or 'none'})."
                    )
                if metro not in metros:
                    metros.append(metro)
            prop.buy_box_metros = metros
            changes.append(f"buy-box metros: {', '.join(metros) or 'none'}")
        else:
            kept = [m for m in (prop.buy_box_metros or []) if m in allowed]
            if kept != list(prop.buy_box_metros or []):
                prop.buy_box_metros = kept
                changes.append(f"buy-box metros: {', '.join(kept) or 'none'}")

    if body.property_type is not None and body.property_type != prop.property_type:
        prop.property_type = body.property_type
        changes.append(f"property type {body.property_type.value}")
    if body.number_of_units is not None and body.number_of_units != prop.number_of_units:
        prop.number_of_units = body.number_of_units
        changes.append(f"{body.number_of_units} units")

    if changes:
        marker = provenance.row_marker_key("property", prop.id)
        if marker not in await provenance.load_manual_rows(db, application.id):
            await provenance.mark_manual_row(db, application.id, "property", prop.id)
        events.add_event(
            db,
            application.id,
            actor=events.actor_for(user_id),
            type=events.PROPERTY_UPDATED,
            payload={
                "property_id": str(prop.id),
                "changes": changes,
                "message": "Property: " + "; ".join(changes),
            },
        )
    await db.flush()
    return changes


async def mark_document(
    db: AsyncSession,
    application: Application,
    document_id: uuid.UUID,
    received: bool,
    user_id: uuid.UUID,
) -> Document:
    document = await db.get(Document, document_id)
    if document is None or document.application_id != application.id:
        raise NotFoundError(f"No document {document_id} on this application.")
    if (document.received_at is not None) == received:
        return document
    document.received_at = now() if received else None
    events.add_event(
        db,
        application.id,
        actor=events.actor_for(user_id),
        type=events.DOCUMENT_RECEIVED,
        payload={
            "document_id": str(document.id),
            "doc_type": document.doc_type,
            "received": received,
            "message": (
                f"Marked {document.doc_type.replace('_', ' ')} received"
                if received
                else f"Marked {document.doc_type.replace('_', ' ')} not received"
            ),
        },
    )
    await db.flush()
    return document
