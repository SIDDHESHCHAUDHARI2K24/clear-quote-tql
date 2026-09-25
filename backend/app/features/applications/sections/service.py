"""Read model for `GET /applications/{id}/sections/{tab}` (CQ-028a).

Each tab returns its records (every field as `{field_key, value, source,
overridden, original_value}`), the tab's open flags, and a tab summary
(housing months, credit/DTI + consent, assets/reserves + documents,
property/buy-box). SSNs are always masked here.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.enums import FieldSource, Occupancy
from app.core.errors import NotFoundError
from app.features.applications.assets.models import Asset, Document, Employment
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.property.models import Property, PropertyAddressStatus
from app.features.applications.sections import provenance
from app.features.applications.sections.fields import (
    APPLICATION_FIELDS,
    PARTY_COLUMNS,
    ROW_COLUMNS,
    base_source,
    party_field_key,
    row_field_key,
    to_json,
)
from app.features.applications.sections.masking import mask_ssn
from app.features.applications.sections.schemas import (
    AssetsSummary,
    ConsentSummary,
    CreditSummary,
    DocumentItem,
    HousingSummary,
    PropertySummary,
    SectionField,
    SectionFlag,
    SectionRecord,
    SectionResponse,
    SectionTab,
)
from app.features.applications.verification.models import FieldValue, Flag
from app.features.applications.verification.service import (
    latest_scenario_snapshot,
    setting_int,
)
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.pricing.engine.borrower_ratios import (
    assets_sufficient,
    debt_to_income_ratio,
    required_funds_amount,
    reserves_required_amount,
)

REQUIRED_HOUSING_MONTHS = 24
"""Same threshold as CQ-012's `housing_history_24mo` rule."""

_PROPERTY_COLUMNS: list[tuple[str, str]] = [
    ("street_address", "Street address"),
    ("city", "City"),
    ("state", "State"),
    ("zip", "Zip"),
    ("county", "County"),
    ("property_type", "Property type"),
    ("number_of_units", "Units"),
]


def fico_bracket(score: int | None) -> str | None:
    """20-point bands, `"<620"` ... `"760–779"`, `"780+"` (plan.md #11)."""
    if score is None:
        return None
    if score >= 780:
        return "780+"
    if score < 620:
        return "<620"
    low = 620 + ((score - 620) // 20) * 20
    return f"{low}–{low + 19}"


class _Ctx:
    """Everything the tab builders share, loaded once per request."""

    def __init__(
        self,
        application: Application,
        overrides: dict[str, FieldValue],
        manual_rows: set[str],
        auto_copied: set[str],
    ) -> None:
        self.application = application
        self.base = base_source(application)
        self.overrides = overrides
        self.manual_rows = manual_rows
        self.auto_copied = auto_copied

    def is_manual(self, collection: str, row_id: uuid.UUID) -> bool:
        return provenance.row_marker_key(collection, row_id) in self.manual_rows

    def field(
        self,
        field_key: str,
        label: str,
        value: Any,
        *,
        base: FieldSource | None = None,
        editable: bool = True,
        mask: bool = False,
    ) -> SectionField:
        override = self.overrides.get(field_key)
        shown = mask_ssn(value) if mask else to_json(value)
        if override is not None:
            stored = provenance.unseal(override.value)
            original = mask_ssn(stored) if mask else stored
            return SectionField(
                field_key=field_key,
                label=label,
                value=shown,
                source=FieldSource.LO_OVERRIDE,
                overridden=True,
                original_value=original,  # type: ignore[arg-type]
                editable=editable,
            )
        return SectionField(
            field_key=field_key,
            label=label,
            value=shown,
            source=base or self.base,
            overridden=False,
            editable=editable,
        )


async def load_application(db: AsyncSession, application_id: uuid.UUID) -> Application:
    application = (
        await db.execute(
            select(Application)
            .where(Application.id == application_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    return application


async def _rows[T](db: AsyncSession, stmt: Any) -> list[T]:
    return list((await db.execute(stmt.execution_options(populate_existing=True))).scalars().all())


# --- borrowers -----------------------------------------------------------------


async def _borrowers(db: AsyncSession, ctx: _Ctx) -> list[SectionRecord]:
    parties: list[ApplicationParty] = await _rows(
        db,
        select(ApplicationParty).where(ApplicationParty.application_id == ctx.application.id),
    )
    parties.sort(key=lambda p: 0 if p.role is PartyRole.BORROWER else 1)
    records: list[SectionRecord] = []
    for party in parties:
        manual = ctx.is_manual("parties", party.id)
        party_base = FieldSource.LO_ENTRY if manual else None
        fields: list[SectionField] = []
        for column_name, column in PARTY_COLUMNS.items():
            key = party_field_key(party.role, column_name)
            value = getattr(party, column.attr)
            base = party_base
            if (
                column_name == "home_phone"
                and key not in ctx.overrides
                and key in ctx.auto_copied
                and value is not None
            ):
                base = FieldSource.FORMULA  # auto-copied from the cell phone (AC3)
            fields.append(ctx.field(key, column.label, value, base=base, mask=column_name == "ssn"))
        records.append(
            SectionRecord(
                kind="party", id=party.id, role=party.role.value, manual=manual, fields=fields
            )
        )
    return records


# --- housing -------------------------------------------------------------------


async def _housing(db: AsyncSession, ctx: _Ctx) -> tuple[list[SectionRecord], HousingSummary]:
    rows: list[HousingHistory] = await _rows(
        db,
        select(HousingHistory)
        .where(HousingHistory.application_id == ctx.application.id)
        .order_by(HousingHistory.sequence),
    )
    records = [_row_record(ctx, "housing_history", "housing_history", row) for row in rows]
    total = sum(row.residence_years * 12 + row.residence_months for row in rows)
    summary = HousingSummary(
        total_months=total,
        required_months=REQUIRED_HOUSING_MONTHS,
        meets_requirement=total >= REQUIRED_HOUSING_MONTHS,
    )
    return records, summary


def _row_record(ctx: _Ctx, collection: str, kind: Any, row: Any) -> SectionRecord:
    manual = ctx.is_manual(collection, row.id)
    fields = [
        ctx.field(
            row_field_key(collection, row.id, name),
            column.label,
            getattr(row, column.attr),
            base=FieldSource.LO_ENTRY if manual else None,
        )
        for name, column in ROW_COLUMNS[collection].items()
    ]
    return SectionRecord(kind=kind, id=row.id, manual=manual, fields=fields)


# --- credit --------------------------------------------------------------------


async def _field_value(
    db: AsyncSession, application_id: uuid.UUID, field_key: str
) -> FieldValue | None:
    return (
        await db.execute(
            select(FieldValue)
            .where(FieldValue.application_id == application_id, FieldValue.field_key == field_key)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def latest_consent(db: AsyncSession, application_id: uuid.UUID) -> Consent | None:
    return (
        (
            await db.execute(
                select(Consent)
                .where(
                    Consent.application_id == application_id, Consent.type == ConsentType.HARD_PULL
                )
                .order_by(Consent.requested_at.desc().nulls_last(), Consent.created_at.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )


def effective_consent_status(consent: Consent) -> ConsentStatus:
    """A pending request past `expires_at` reads as expired (plan.md #13);
    CQ-033 owns persisting that."""
    if (
        consent.status is ConsentStatus.PENDING
        and consent.expires_at is not None
        and consent.expires_at <= now()
    ):
        return ConsentStatus.EXPIRED
    return consent.status


def consent_summary(consent: Consent, fico: int | None, pull_type: str | None) -> ConsentSummary:
    status = effective_consent_status(consent)
    return ConsentSummary(
        id=consent.id,
        status=status,
        requested_at=consent.requested_at,
        requested_by=consent.requested_by,
        expires_at=consent.expires_at,
        decided_at=consent.decided_at,
        decline_reason=consent.decline_reason,
        fico_after_pull=(
            fico if status is ConsentStatus.ACCEPTED and pull_type == "hard_pull" else None
        ),
    )


async def _sum(db: AsyncSession, column: Any, where: Any) -> Decimal:
    value = (await db.execute(select(func.sum(column)).where(where))).scalar_one_or_none()
    return Decimal(value) if value is not None else Decimal("0")


async def _credit(db: AsyncSession, ctx: _Ctx) -> tuple[list[SectionRecord], CreditSummary]:
    app = ctx.application
    fico_row = await _field_value(db, app.id, "representative_fico")
    pull_type_row = await _field_value(db, app.id, "credit_pull_type")
    fico = int(str(fico_row.value)) if fico_row is not None and fico_row.value is not None else None
    pull_type: str | None = None
    if fico_row is not None:
        hard = fico_row.source_ref == "hard_pull" or (
            pull_type_row is not None and str(pull_type_row.value).lower() == "hard_pull"
        )
        pull_type = "hard_pull" if hard else "soft_pull"

    credit_record = SectionRecord(
        kind="credit",
        id=None,
        fields=[
            SectionField(
                field_key="representative_fico",
                label="Representative FICO",
                value=fico,
                source=fico_row.source if fico_row is not None else ctx.base,
                overridden=False,
                editable=False,
            ),
            SectionField(
                field_key="credit_score_bracket",
                label="FICO bracket",
                value=fico_bracket(fico),
                source=FieldSource.FORMULA,
                overridden=False,
                editable=False,
            ),
        ],
    )

    liabilities: list[Liability] = await _rows(
        db,
        select(Liability)
        .where(Liability.application_id == app.id)
        .order_by(Liability.created_at, Liability.creditor_name),
    )
    records = [credit_record] + [
        _row_record(ctx, "liabilities", "liability", row) for row in liabilities
    ]
    liabilities_total = sum((row.monthly_payment for row in liabilities), start=_zero())

    dti_applicable = app.occupancy is Occupancy.PRIMARY
    dti = None
    dti_status: Any = "not_applicable"
    if dti_applicable:
        income = await _sum(db, Employment.monthly_income, Employment.application_id == app.id)
        scenario = await latest_scenario_snapshot(db, app.id)
        if income <= 0:
            dti_status = "no_income"
        elif scenario is None:
            dti_status = "awaiting_pricing"
        else:
            dti = debt_to_income_ratio(liabilities_total, scenario.total_monthly_payment, income)
            dti_status = "ok" if dti is not None else "no_income"

    consent = await latest_consent(db, app.id)
    summary = CreditSummary(
        representative_fico=fico,
        fico_bracket=fico_bracket(fico),
        pull_type=pull_type,  # type: ignore[arg-type]
        pulled_at=fico_row.updated_at if fico_row is not None else None,
        liabilities_monthly_total=liabilities_total,
        dti_applicable=dti_applicable,
        dti=dti,
        dti_status=dti_status,
        consent=consent_summary(consent, fico, pull_type) if consent is not None else None,
    )
    return records, summary


def _zero() -> Decimal:
    return Decimal("0.00")


# --- assets --------------------------------------------------------------------


async def _assets(db: AsyncSession, ctx: _Ctx) -> tuple[list[SectionRecord], AssetsSummary]:
    app = ctx.application
    assets: list[Asset] = await _rows(
        db, select(Asset).where(Asset.application_id == app.id).order_by(Asset.created_at)
    )
    records = [_row_record(ctx, "assets", "asset", row) for row in assets]

    income_applicable = app.occupancy is Occupancy.PRIMARY
    income_total = None
    if income_applicable:
        employment: list[Employment] = await _rows(
            db,
            select(Employment)
            .where(Employment.application_id == app.id)
            .order_by(Employment.created_at),
        )
        records += [_row_record(ctx, "employment", "employment", row) for row in employment]
        income_total = sum(
            (row.monthly_income for row in employment if row.monthly_income is not None),
            start=_zero(),
        )

    documents: list[Document] = await _rows(
        db,
        select(Document)
        .where(Document.application_id == app.id)
        .order_by(Document.doc_type, Document.created_at),
    )

    assets_total = sum((row.verified_amount for row in assets), start=_zero())
    reserves_key = (
        "reserves_months_primary"
        if app.occupancy is Occupancy.PRIMARY
        else "reserves_months_investment"
    )
    reserves_months = await setting_int(db, reserves_key)
    scenario = await latest_scenario_snapshot(db, app.id)
    reserves_required = cash_to_close = required = None
    status: Any = "awaiting_pricing"
    if scenario is not None:
        reserves_required = reserves_required_amount(
            reserves_months, scenario.total_monthly_payment
        )
        cash_to_close = scenario.total_cash_to_close
        required = required_funds_amount(cash_to_close, reserves_required)
        status = "sufficient" if assets_sufficient(assets_total, required) else "insufficient"

    summary = AssetsSummary(
        verified_assets_total=assets_total,
        reserves_months=reserves_months,
        reserves_required=reserves_required,
        cash_to_close=cash_to_close,
        required_funds=required,
        status=status,
        income_applicable=income_applicable,
        monthly_income_total=income_total,
        documents=[
            DocumentItem(
                id=doc.id,
                doc_type=doc.doc_type,
                received=doc.received_at is not None,
                received_at=doc.received_at,
            )
            for doc in documents
        ],
    )
    return records, summary


# --- property ------------------------------------------------------------------


async def _property(
    db: AsyncSession, ctx: _Ctx
) -> tuple[list[SectionRecord], PropertySummary | None]:
    app = ctx.application
    loan_record = SectionRecord(
        kind="loan",
        id=app.id,
        fields=[
            ctx.field(key, column.label, getattr(app, column.attr))
            for key, column in APPLICATION_FIELDS.items()
        ],
    )
    prop = (
        await db.execute(
            select(Property)
            .where(Property.application_id == app.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if prop is None:
        return [loan_record], None
    edited = ctx.is_manual("property", prop.id)
    property_record = SectionRecord(
        kind="property",
        id=prop.id,
        manual=edited,
        fields=[
            ctx.field(
                f"property.{name}",
                label,
                getattr(prop, name),
                base=FieldSource.LO_ENTRY if edited else None,
                editable=False,  # edited through PATCH /property
            )
            for name, label in _PROPERTY_COLUMNS
        ],
    )
    summary = PropertySummary(
        tbd=prop.address_status is PropertyAddressStatus.TBD,
        recommend_matches=prop.recommend_matches,
        buy_box_states=list(prop.buy_box_states or []),
        buy_box_metros=list(prop.buy_box_metros or []),
    )
    return [property_record, loan_record], summary


# --- entry point ---------------------------------------------------------------


async def build_section(
    db: AsyncSession, application_id: uuid.UUID, tab: SectionTab
) -> SectionResponse:
    application = await load_application(db, application_id)
    ctx = _Ctx(
        application,
        await provenance.load_overrides(db, application_id),
        await provenance.load_manual_rows(db, application_id),
        await provenance.load_auto_markers(db, application_id),
    )

    response = SectionResponse(
        application_id=application.id,
        tab=tab,
        status=application.status,
        occupancy=application.occupancy,
        records=[],
        flags=[],
    )
    if tab is SectionTab.BORROWERS:
        response.records = await _borrowers(db, ctx)
    elif tab is SectionTab.HOUSING:
        response.records, response.housing = await _housing(db, ctx)
    elif tab is SectionTab.CREDIT:
        response.records, response.credit = await _credit(db, ctx)
    elif tab is SectionTab.ASSETS:
        response.records, response.assets = await _assets(db, ctx)
    else:
        response.records, response.property = await _property(db, ctx)

    field_keys = {f.field_key for record in response.records for f in record.fields}
    flags: list[Flag] = await _rows(
        db,
        select(Flag)
        .where(Flag.application_id == application_id, Flag.resolved_at.is_(None))
        .order_by(Flag.created_at),
    )
    response.flags = [
        SectionFlag(
            id=flag.id,
            tab=flag.tab,
            field_key=flag.field_key,
            rule=flag.rule,
            severity=flag.severity,
            message=flag.message,
        )
        for flag in flags
        if flag.tab.value == tab.value or flag.field_key in field_keys
    ]
    return response
