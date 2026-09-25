"""Apply wizard service (CQ-032a): drafts, autosave, submit.

Submit writes the same rows `applications.service.import_from_los` writes
for an LOS loan (parties, housing, employment, liabilities, assets,
`occupancy`, `field_values.representative_fico` from a soft pull) plus the
property, then assigns the least-loaded LO, emails them, records the
consent and starts the CQ-011 pipeline. `applications.source = portal`
makes the pipeline skip its import stage (foundation E14). See
docs/backlog/CQ-032-apply-wizard/plan.md for every decision referenced
below by number.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client as TemporalClient
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.core import clock, storage
from app.core.enums import ApplicationSource, ApplicationStatus, FieldSource, Occupancy, Strategy
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationAppError
from app.features.applications.assets.models import Asset, Document, Employment
from app.features.applications.assignment import INACTIVE_STATUSES, least_loaded_lo_id
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import (
    Application,
    ApplicationParty,
    MaritalStatus,
    PartyRole,
)
from app.features.applications.property.models import (
    Property,
    PropertyAddressStatus,
    PropertyType,
)
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import BorrowerAccount, User
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.clients.models import Client
from app.features.notifications.email.service import send_email
from app.integrations.common.errors import CreditPullFailedError, ProviderUnavailableError
from app.integrations.credit.mock import MockCreditClient, portal_credit_key
from app.integrations.credit.models import CreditPullType
from app.integrations.property_search.models import ProviderListing
from app.integrations.tax.models import ProviderTaxRate
from app.workflows.application_pipeline import ApplicationPipelineWorkflow
from app.workflows.constants import APPLICATION_PIPELINE_TASK_QUEUE, application_workflow_id

from . import templates
from .consent_text import CONSENT_TEXT, CONSENT_TEXT_VERSION, consent_text_hash
from .models import ApplicationDraft
from .schemas import (
    ApplyDraftOut,
    ConsentTextOut,
    DraftPatchResponse,
    DraftTabs,
    SubmitResponse,
    TabStatus,
)
from .validation import (
    TAB_ORDER,
    ConsentTab,
    IncomeTab,
    PropertyTab,
    TabName,
    YouTab,
    context_for,
    first_incomplete_tab,
    validate_all,
    validate_tab,
)

logger = logging.getLogger(__name__)

MAX_TAB_BYTES = 64 * 1024
DOCUMENTS_KEY = "documents"
SOURCE_REF_PORTAL = "borrower_portal"
_ACTOR_BORROWER = "borrower"
_ACTOR_SYSTEM = "system"

TemporalClientFactory = Callable[[], Awaitable[TemporalClient]]

_OCCUPANCY_LABEL = {
    "primary": "Primary residence",
    "ltr": "Long-term rental",
    "str": "Short-term rental",
}


# ---------------------------------------------------------------- drafts


async def known_metros(db: AsyncSession) -> dict[str, frozenset[str]]:
    """State -> metro names offered by the two-tier picker (plan.md #11),
    from the mock property-search provider's listings."""
    rows = (await db.execute(select(ProviderListing.state, ProviderListing.metro).distinct())).all()
    by_state: dict[str, set[str]] = {}
    for state, metro in rows:
        by_state.setdefault(state, set()).add(metro)
    return {state: frozenset(metros) for state, metros in by_state.items()}


async def get_owned_draft(
    db: AsyncSession, account: BorrowerAccount, draft_id: uuid.UUID, *, for_update: bool = False
) -> ApplicationDraft:
    """The draft, only when `account` owns it; else 404 (plan.md #2)."""
    stmt = select(ApplicationDraft).where(
        ApplicationDraft.id == draft_id,
        ApplicationDraft.borrower_account_id == account.id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    draft = (await db.execute(stmt)).scalar_one_or_none()
    if draft is None:
        raise NotFoundError("Application not found")
    return draft


def _ensure_open(draft: ApplicationDraft) -> None:
    if draft.submitted_application_id is not None:
        raise ConflictError(
            "This application was already submitted.",
            details={"application_id": str(draft.submitted_application_id)},
        )


async def _open_draft_for(db: AsyncSession, account: BorrowerAccount) -> ApplicationDraft | None:
    return (
        await db.execute(
            select(ApplicationDraft).where(
                ApplicationDraft.borrower_account_id == account.id,
                ApplicationDraft.submitted_application_id.is_(None),
            )
        )
    ).scalar_one_or_none()


async def get_or_create_draft(db: AsyncSession, account: BorrowerAccount) -> ApplicationDraft:
    """The borrower's one open draft, created when none exists (one open
    draft per borrower: the partial unique index backs this up)."""
    existing = await _open_draft_for(db, account)
    if existing is not None:
        return existing
    draft = ApplicationDraft(borrower_account_id=account.id, data={}, current_tab=TabName.YOU)
    db.add(draft)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # A concurrent request created it first.
        existing = await _open_draft_for(db, account)
        if existing is None:
            raise
        return existing
    await db.commit()
    await db.refresh(draft)
    return draft


def _public_data(data: dict[str, Any]) -> dict[str, Any]:
    """The draft data as returned to the borrower: storage keys stripped
    from the document list."""
    income = data.get(TabName.INCOME.value)
    if not isinstance(income, dict) or not isinstance(income.get(DOCUMENTS_KEY), list):
        return data
    documents = [
        {k: v for k, v in doc.items() if k != "object_key"} for doc in income[DOCUMENTS_KEY]
    ]
    return {**data, TabName.INCOME.value: {**income, DOCUMENTS_KEY: documents}}


async def draft_out(
    db: AsyncSession, draft: ApplicationDraft, account: BorrowerAccount
) -> ApplyDraftOut:
    data = draft.data or {}
    _, failures = validate_all(data, context_for(data, await known_metros(db)))
    return ApplyDraftOut(
        id=draft.id,
        email=account.email,
        current_tab=TabName(draft.current_tab),
        tabs=DraftTabs(**{tab.value: TabStatus(complete=tab not in failures) for tab in TAB_ORDER}),
        data=_public_data(data),
        submitted_application_id=draft.submitted_application_id,
        consent=ConsentTextOut(version=CONSENT_TEXT_VERSION, text=CONSENT_TEXT),
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def _documents_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    income = data.get(TabName.INCOME.value)
    if isinstance(income, dict) and isinstance(income.get(DOCUMENTS_KEY), list):
        return list(income[DOCUMENTS_KEY])
    return []


def _with_documents(data: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    income = data.get(TabName.INCOME.value)
    income = dict(income) if isinstance(income, dict) else {}
    income[DOCUMENTS_KEY] = documents
    return {**data, TabName.INCOME.value: income}


async def _store_data(db: AsyncSession, draft: ApplicationDraft, data: dict[str, Any]) -> None:
    """Writes `data` and recomputes the resume tab (plan.md #4)."""
    _, failures = validate_all(data, context_for(data, await known_metros(db)))
    draft.data = data
    draft.current_tab = first_incomplete_tab(failures).value
    draft.updated_at = clock.now()
    await db.flush()


async def save_tab(
    db: AsyncSession,
    account: BorrowerAccount,
    draft_id: uuid.UUID,
    tab: TabName,
    tab_data: dict[str, Any],
) -> DraftPatchResponse:
    """Autosaves one tab (replacing it wholesale), then validates it. A
    validation failure never blocks the save (plan.md #3)."""
    if len(json.dumps(tab_data, default=str)) > MAX_TAB_BYTES:
        raise ValidationAppError("This step has too much data to save.")
    draft = await get_owned_draft(db, account, draft_id, for_update=True)
    _ensure_open(draft)

    incoming = dict(tab_data)
    if tab is TabName.YOU:
        incoming.pop("email", None)  # read-only: always the account email
    if tab is TabName.INCOME:
        incoming[DOCUMENTS_KEY] = _documents_of(draft.data or {})  # server-managed

    data = {**(draft.data or {}), tab.value: incoming}
    await _store_data(db, draft, data)
    await db.commit()
    await db.refresh(draft)

    metros = await known_metros(db)
    _, errors = validate_tab(tab, incoming, context_for(data, metros))
    return DraftPatchResponse(
        draft=await draft_out(db, draft, account),
        tab=tab,
        tab_valid=not errors,
        field_errors=errors,
    )


# ---------------------------------------------------------------- submit


def _money(value: Decimal) -> str:
    return f"${value:,.0f}"


async def _county_for(db: AsyncSession, state: str, zip_code: str) -> str | None:
    """County for a specific address (plan.md #11): the listing provider's
    county for that ZIP, else the only tax-rate county in the state."""
    county = (
        await db.execute(
            select(ProviderListing.county)
            .where(ProviderListing.zip == zip_code, ProviderListing.state == state)
            .limit(1)
        )
    ).scalar_one_or_none()
    if county is not None:
        return county
    counties = (
        (await db.execute(select(ProviderTaxRate.county).where(ProviderTaxRate.state == state)))
        .scalars()
        .all()
    )
    return counties[0] if len(set(counties)) == 1 else None


async def _build_property(
    db: AsyncSession, application_id: uuid.UUID, prop: PropertyTab
) -> Property:
    if prop.has_property and prop.address is not None:
        return Property(
            application_id=application_id,
            address_status=PropertyAddressStatus.SPECIFIC_ADDRESS,
            street_address=prop.address.street,
            city=prop.address.city,
            state=prop.address.state,
            zip=prop.address.zip,
            county=await _county_for(db, prop.address.state, prop.address.zip),
            property_type=PropertyType.SINGLE_FAMILY,
            number_of_units=1,
            buy_box_states=[],
            buy_box_metros=[],
            recommend_matches=False,
        )
    # TBD: the first metro's representative listing supplies the market
    # city/state/zip/county the pricing chain needs (the seed does the
    # same for TBD personas).
    listing = (
        await db.execute(
            select(ProviderListing)
            .where(
                ProviderListing.metro == prop.buy_box_metros[0],
                ProviderListing.state.in_(prop.buy_box_states),
            )
            .order_by(ProviderListing.zip, ProviderListing.address)
            .limit(1)
        )
    ).scalar_one_or_none()
    return Property(
        application_id=application_id,
        address_status=PropertyAddressStatus.TBD,
        street_address=None,
        city=listing.city if listing else None,
        state=listing.state if listing else next(iter(prop.buy_box_states), None),
        zip=listing.zip if listing else None,
        county=listing.county if listing else None,
        property_type=PropertyType.SINGLE_FAMILY,
        number_of_units=1,
        buy_box_states=prop.buy_box_states,
        buy_box_metros=prop.buy_box_metros,
        recommend_matches=True,
    )


def _party(
    application_id: uuid.UUID,
    role: PartyRole,
    person: Any,
    *,
    email: str | None,
    no_co_applicant: bool = False,
) -> ApplicationParty:
    return ApplicationParty(
        application_id=application_id,
        role=role,
        first_name=person.first_name,
        last_name=person.last_name,
        ssn_encrypted=person.ssn,
        dob=person.dob,
        marital_status=MaritalStatus(person.marital_status),
        dependents_count=person.dependents_count,
        email=email,
        cell_phone=person.cell_phone,
        no_co_applicant_check=no_co_applicant,
    )


def _housing_rows(application_id: uuid.UUID, you: YouTab) -> list[HousingHistory]:
    rows = [
        HousingHistory(
            application_id=application_id,
            sequence=0,
            street_address=you.current_address.street,
            city=you.current_address.city,
            state=you.current_address.state,
            zip=you.current_address.zip,
            housing_status=HousingStatus(you.housing_status),
            residence_years=you.residence_years,
            residence_months=you.residence_months,
            vom_completed=False,
        )
    ]
    if you.prior_address is not None:
        prior = you.prior_address
        rows.append(
            HousingHistory(
                application_id=application_id,
                sequence=1,
                street_address=prior.street,
                city=prior.city,
                state=prior.state,
                zip=prior.zip,
                housing_status=HousingStatus.RENT,
                residence_years=prior.residence_years,
                residence_months=prior.residence_months,
                vom_completed=False,
            )
        )
    return rows


async def _soft_pull_fico(db: AsyncSession, application_id: uuid.UUID) -> int | None:
    """E14 / plan.md #12: the soft pull `import_from_los` does, keyed by
    the portal credit key. A provider outage leaves the score unset, so
    the pipeline's validate stage flags the missing FICO for the LO."""
    try:
        report = await MockCreditClient(db).pull_credit(
            portal_credit_key(application_id), CreditPullType.SOFT_PULL
        )
    except (ProviderUnavailableError, CreditPullFailedError):
        logger.warning("Soft pull failed for portal application %s", application_id)
        return None
    return report.experian_score


async def _move_documents(
    db: AsyncSession, application_id: uuid.UUID, documents: list[dict[str, Any]]
) -> list[str]:
    """Copies each draft upload to `applications/{id}/documents/` and
    creates its `documents` row (plan.md #19). Returns the draft keys to
    delete once the application commits."""
    moved: list[str] = []
    for doc in documents:
        source_key = str(doc["object_key"])
        stored = await storage.get_object(source_key)
        suffix = source_key.rsplit("/", 1)[-1]
        target_key = f"applications/{application_id}/documents/{suffix}"
        await storage.put_object(
            target_key, stored.body, stored.content_type or str(doc["content_type"])
        )
        db.add(
            Document(
                application_id=application_id,
                doc_type=str(doc["doc_type"]),
                object_key=target_key,
                received_at=clock.now(),
            )
        )
        moved.append(source_key)
    return moved


async def _start_pipeline(client_factory: TemporalClientFactory, application_id: uuid.UUID) -> bool:
    """Starts CQ-011's workflow exactly like `applications/router.py`
    (plan.md #17). Never raises: a Temporal outage leaves the application
    in Intake for the LO to re-trigger."""
    try:
        client = await client_factory()
        await client.start_workflow(
            ApplicationPipelineWorkflow.run,
            str(application_id),
            id=application_workflow_id(str(application_id)),
            task_queue=APPLICATION_PIPELINE_TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        return True
    except Exception:
        logger.exception("Could not start the pipeline for application %s", application_id)
        return False
    return True


async def submit(
    db: AsyncSession,
    account: BorrowerAccount,
    draft_id: uuid.UUID,
    *,
    client_factory: TemporalClientFactory,
    ip: str,
    user_agent: str | None,
) -> SubmitResponse:
    draft = await get_owned_draft(db, account, draft_id, for_update=True)
    _ensure_open(draft)
    data = draft.data or {}
    parsed, failures = validate_all(data, context_for(data, await known_metros(db)))
    if failures:
        raise ValidationAppError(
            "Some steps still need attention.",
            details={
                "field_errors": {tab.value: errs for tab, errs in failures.items()},
                "first_invalid_tab": first_incomplete_tab(failures).value,
            },
        )
    you = cast(YouTab, parsed[TabName.YOU])
    prop = cast(PropertyTab, parsed[TabName.PROPERTY])
    income = cast(IncomeTab, parsed[TabName.INCOME])
    consent = cast(ConsentTab, parsed[TabName.CONSENT])

    client = await db.get(Client, account.client_id)
    if client is None:
        raise NotFoundError("Client not found")
    lo_id = await least_loaded_lo_id(db)
    lo = await db.get(User, lo_id) if lo_id is not None else None
    if lo is None:
        raise AppError(
            "No loan officer is available right now. Please try again later.",
            code="NO_LO_AVAILABLE",
            status_code=409,
        )
    now = clock.now()

    # Plan.md #16: the client follows the new LO unless another active
    # application already ties it to someone.
    other_active = (
        await db.execute(
            select(func.count())
            .select_from(Application)
            .where(
                Application.client_id == client.id,
                Application.status.not_in(INACTIVE_STATUSES),
            )
        )
    ).scalar_one()
    if other_active == 0:
        client.assigned_lo_id = lo.id
    if not client.phone:
        client.phone = you.cell_phone

    is_primary = prop.occupancy == "primary"
    application = Application(
        client_id=client.id,
        lo_id=lo.id,
        los_loan_guid=None,
        status=ApplicationStatus.INTAKE,
        occupancy=Occupancy.PRIMARY if is_primary else Occupancy.INVESTMENT,
        strategy=None if is_primary else Strategy(prop.occupancy),
        requested_price=prop.target_price,
        source=ApplicationSource.PORTAL,
    )
    db.add(application)
    await db.flush()
    app_id = application.id

    property_ = await _build_property(db, app_id, prop)
    application.subject_state = property_.state
    db.add(property_)

    db.add(
        _party(
            app_id,
            PartyRole.BORROWER,
            you,
            email=account.email,
            no_co_applicant=not you.has_co_borrower,
        )
    )
    if you.has_co_borrower and you.co_borrower is not None:
        db.add(_party(app_id, PartyRole.CO_BORROWER, you.co_borrower, email=you.co_borrower.email))
    for row in _housing_rows(app_id, you):
        db.add(row)

    if income.employer_name is not None or income.monthly_income is not None:
        db.add(
            Employment(
                application_id=app_id,
                employer_name=income.employer_name,
                monthly_income=income.monthly_income,
                years_at_job=income.years_employed,
                self_employed=False,
            )
        )
    if income.monthly_debts is not None and income.monthly_debts > 0:
        db.add(
            Liability(
                application_id=app_id,
                creditor_name="Self-reported debts",
                account_type="self_reported",
                monthly_payment=income.monthly_debts,
                balance=Decimal("0"),
            )
        )
    db.add(
        Asset(
            application_id=app_id,
            account_type="liquid",
            institution="Borrower reported",
            verified_amount=income.liquid_assets,
        )
    )

    db.add(
        FieldValue(
            application_id=app_id,
            field_key="down_payment_pct",
            value=str(prop.down_payment_pct),
            source=FieldSource.LO_ENTRY,
            source_ref=SOURCE_REF_PORTAL,
        )
    )
    fico = await _soft_pull_fico(db, app_id)
    if fico is not None:
        db.add(
            FieldValue(
                application_id=app_id,
                field_key="representative_fico",
                value=fico,
                source=FieldSource.CREDIT_BUREAU,
                source_ref="soft_pull",
            )
        )

    db.add(
        Consent(
            application_id=app_id,
            type=ConsentType.APPLICATION,
            status=ConsentStatus.ACCEPTED,
            requested_at=now,
            decided_at=now,
            at=now,
            text_version=CONSENT_TEXT_VERSION,
            text_hash=consent_text_hash(),
            typed_name=consent.typed_name,
            ip=ip,
            user_agent=user_agent,
        )
    )

    draft_keys = await _move_documents(db, app_id, _documents_of(data))

    borrower_name = you.full_name
    db.add(
        ActivityEvent(
            application_id=app_id,
            actor=_ACTOR_BORROWER,
            type="application.submitted",
            payload={"source": ApplicationSource.PORTAL.value, "draft_id": str(draft.id)},
            at=now,
        )
    )
    db.add(
        ActivityEvent(
            application_id=app_id,
            actor=_ACTOR_SYSTEM,
            type="application.assigned",
            payload={"lo_id": str(lo.id), "lo_name": lo.full_name, "rule": "least_loaded"},
            at=now,
        )
    )

    location = (
        f"{prop.address.street}, {prop.address.city}, {prop.address.state} {prop.address.zip}"
        if prop.has_property and prop.address is not None
        else f"To be determined: {', '.join(prop.buy_box_metros)}"
    )
    draft.submitted_application_id = app_id
    draft.updated_at = now
    await db.commit()

    # The LO email goes out only once the application exists (SMTP sends
    # immediately; a rolled-back submit must not have emailed anyone). Its
    # outbox row commits on its own right after.
    await send_email(
        db,
        to=lo.email,
        subject=templates.new_application_subject(borrower_name),
        html=templates.new_application_html(
            lo_name=lo.full_name,
            borrower_name=borrower_name,
            borrower_email=account.email,
            goal=_OCCUPANCY_LABEL[prop.occupancy],
            price=_money(prop.target_price),
            location=location,
        ),
        application_id=app_id,
    )
    await db.commit()

    for key in draft_keys:
        try:
            await storage.delete_object(key)
        except Exception:
            logger.warning("Could not delete draft upload %s", key, exc_info=True)

    started = await _start_pipeline(client_factory, app_id)
    return SubmitResponse(
        application_id=app_id,
        draft_id=draft.id,
        status="intake",
        assigned_lo_name=lo.full_name,
        pipeline_started=started,
    )
