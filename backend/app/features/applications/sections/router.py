"""Verification-tab API (CQ-028a): section reads, field and row edits, SSN
reveal, credit/property actions and document receipt.

Every route is scoped with `get_scoped_application` (404 out of scope,
E16). Every write commits, then runs the re-verify/resume hook
(`reverify.reverify_and_maybe_resume`) and returns the refreshed section
with `resume` set, so the UI can re-render flags and show the "pricing
resumed" toast from one response.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, get_scoped_application
from app.core.db import get_db
from app.core.errors import NotFoundError
from app.features.applications.locking import lock_application
from app.features.applications.models import Application, ApplicationParty
from app.features.applications.sections import collections, credit, events, fields, property
from app.features.applications.sections.reverify import (
    TemporalProvider,
    get_temporal_provider,
    reverify_and_maybe_resume,
)
from app.features.applications.sections.schemas import (
    DocumentPatch,
    FieldEditRequest,
    HardPullRequestResponse,
    HousingCreate,
    HousingPatch,
    LiabilityCreate,
    LiabilityPatch,
    PartyCreate,
    PartyPatch,
    PropertyPatch,
    ResumeResult,
    SectionResponse,
    SectionTab,
    SsnRevealResponse,
)
from app.features.applications.sections.service import (
    build_section,
    consent_summary,
)

router = APIRouter(tags=["verification"])

_BASE = "/applications/{application_id}"


async def _lock(db: AsyncSession, application: Application) -> None:
    """Serialises writes for one application (review M1): takes the row lock,
    then reloads the application, which was read before the lock."""
    await lock_application(db, application.id)
    await db.refresh(application)


async def _after_edit(
    db: AsyncSession,
    application_id: uuid.UUID,
    tab: SectionTab,
    temporal: TemporalProvider,
) -> SectionResponse:
    await db.commit()
    outcome = await reverify_and_maybe_resume(db, application_id, temporal)
    section = await build_section(db, application_id, tab)
    # Signal/start last: the resumed pipeline writes to this application.
    sent = await outcome.send()
    if outcome.requested and not sent.requested:
        # The "pricing resumed" event is already committed; record that the
        # Temporal call then failed so the timeline is not misleading.
        events.add_event(
            db,
            application_id,
            actor=events.SYSTEM_ACTOR,
            type=events.RESUME_FAILED,
            payload={"message": "Could not resume pricing: the workflow service is unavailable"},
        )
        await db.commit()
    outcome = sent
    section.resume = ResumeResult(requested=outcome.requested, reason=outcome.reason)
    return section


@router.get(f"{_BASE}/sections/{{tab}}", response_model=SectionResponse)
async def get_section(
    tab: SectionTab,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> SectionResponse:
    return await build_section(db, application.id, tab)


# --- field edits ---------------------------------------------------------------


@router.put(f"{_BASE}/fields/{{field_key}}", response_model=SectionResponse)
async def put_field(
    field_key: str,
    body: FieldEditRequest,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    resolved = await fields.apply_field_edit(db, application, field_key, body.value, user.id)
    return await _after_edit(db, application.id, SectionTab(resolved.tab.value), temporal)


@router.delete(f"{_BASE}/fields/{{field_key}}", response_model=SectionResponse)
async def revert_field(
    field_key: str,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    resolved = await fields.revert_field(db, application, field_key, user.id)
    return await _after_edit(db, application.id, SectionTab(resolved.tab.value), temporal)


@router.post(
    f"{_BASE}/parties/{{party_id}}/ssn-reveal",
    response_model=SsnRevealResponse,
)
async def reveal_ssn(
    party_id: uuid.UUID,
    response: Response,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> SsnRevealResponse:
    await _lock(db, application)
    party = await db.get(ApplicationParty, party_id)
    if party is None or party.application_id != application.id:
        raise NotFoundError(f"No party {party_id} on this application.")
    events.add_event(
        db,
        application.id,
        actor=events.actor_for(user.id),
        type=events.SSN_REVEALED,
        payload={
            "party_id": str(party.id),
            "field_key": fields.party_field_key(party.role, "ssn"),
            "message": f"Revealed the SSN of {party.first_name} {party.last_name}",
        },
    )
    ssn = party.ssn_encrypted
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return SsnRevealResponse(party_id=party.id, ssn=ssn)


# --- row edits -----------------------------------------------------------------


@router.post(f"{_BASE}/housing_history", response_model=SectionResponse, status_code=201)
async def add_housing(
    body: HousingCreate,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await collections.add_housing(db, application, body, user.id)
    return await _after_edit(db, application.id, SectionTab.HOUSING, temporal)


@router.patch(f"{_BASE}/housing_history/{{row_id}}", response_model=SectionResponse)
async def patch_housing(
    row_id: uuid.UUID,
    body: HousingPatch,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await collections.patch_row(
        db, application, "housing_history", row_id, body.model_dump(exclude_unset=True), user.id
    )
    return await _after_edit(db, application.id, SectionTab.HOUSING, temporal)


@router.post(f"{_BASE}/parties", response_model=SectionResponse, status_code=201)
async def add_party(
    body: PartyCreate,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await collections.add_co_borrower(db, application, body, user.id)
    return await _after_edit(db, application.id, SectionTab.BORROWERS, temporal)


@router.patch(f"{_BASE}/parties/{{party_id}}", response_model=SectionResponse)
async def patch_party(
    party_id: uuid.UUID,
    body: PartyPatch,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await collections.patch_party(
        db, application, party_id, body.model_dump(exclude_unset=True), user.id
    )
    return await _after_edit(db, application.id, SectionTab.BORROWERS, temporal)


@router.post(f"{_BASE}/liabilities", response_model=SectionResponse, status_code=201)
async def add_liability(
    body: LiabilityCreate,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await collections.add_liability(db, application, body, user.id)
    return await _after_edit(db, application.id, SectionTab.CREDIT, temporal)


@router.patch(f"{_BASE}/liabilities/{{row_id}}", response_model=SectionResponse)
async def patch_liability(
    row_id: uuid.UUID,
    body: LiabilityPatch,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await collections.patch_row(
        db, application, "liabilities", row_id, body.model_dump(exclude_unset=True), user.id
    )
    return await _after_edit(db, application.id, SectionTab.CREDIT, temporal)


# --- credit actions ------------------------------------------------------------


@router.post(f"{_BASE}/credit/import-liabilities", response_model=SectionResponse)
async def import_liabilities(
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await credit.import_liabilities(db, application, user.id)
    return await _after_edit(db, application.id, SectionTab.CREDIT, temporal)


@router.post(
    f"{_BASE}/credit/hard-pull-request",
    response_model=HardPullRequestResponse,
    status_code=201,
)
async def request_hard_pull(
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> HardPullRequestResponse:
    await _lock(db, application)
    consent = await credit.request_hard_pull(db, application, user.id)
    await db.commit()
    section = await build_section(db, application.id, SectionTab.CREDIT)
    return HardPullRequestResponse(
        consent=consent_summary(consent, None, None),
        section=section,
    )


# --- property + documents ------------------------------------------------------


@router.patch(f"{_BASE}/property", response_model=SectionResponse)
async def patch_property(
    body: PropertyPatch,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
    temporal: TemporalProvider = Depends(get_temporal_provider),
) -> SectionResponse:
    await _lock(db, application)
    await property.update_property(db, application, body, user.id)
    return await _after_edit(db, application.id, SectionTab.PROPERTY, temporal)


@router.patch(f"{_BASE}/documents/{{document_id}}", response_model=SectionResponse)
async def patch_document(
    document_id: uuid.UUID,
    body: DocumentPatch,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_scoped_application),
) -> SectionResponse:
    await _lock(db, application)
    await property.mark_document(db, application, document_id, body.received, user.id)
    await db.commit()
    return await build_section(db, application.id, SectionTab.ASSETS)
