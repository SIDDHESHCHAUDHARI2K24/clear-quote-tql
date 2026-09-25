"""Editable 1003 fields: key registry, parsing, and the edit/revert engine
(plan.md Decisions #3-#5).

Field keys (plan.md #4):

- application: `occupancy_type`, `investment_strategy`
- party: `{role}_{column}` with role `borrower` / `co_borrower`
  (`borrower_cell_phone`, `co_borrower_ssn`, ...)
- rows: `{collection}.{row_id}.{column}` for `housing_history`,
  `liabilities`, `assets`, `employment`

`apply_field_edit` / `revert_field` write the domain column, the `orig:`
provenance row and one activity event; they never commit (the router
commits, then runs the re-verify hook).
"""

from __future__ import annotations

import enum
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ApplicationSource,
    ApplicationTab,
    FieldSource,
    Occupancy,
    Strategy,
)
from app.core.errors import NotFoundError, ValidationAppError
from app.features.applications.assets.models import Asset, Employment
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import (
    Application,
    ApplicationParty,
    BusinessVesting,
    MaritalStatus,
    PartyRole,
)
from app.features.applications.sections import events, provenance
from app.features.applications.sections.masking import mask_ssn

Parser = Callable[[Any], Any]


# --- parsers ---------------------------------------------------------------


def _bad(label: str, why: str) -> ValidationAppError:
    return ValidationAppError(f"{label}: {why}")


def _text(required: bool = False) -> Parser:
    def parse(raw: Any) -> str | None:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if required:
                raise ValueError("is required")
            return None
        if not isinstance(raw, str):
            raise ValueError("must be text")
        return raw.strip()

    return parse


def _state(raw: Any) -> str:
    value = _text()(raw)
    if value is None:
        raise ValueError("is required")
    if not re.fullmatch(r"[A-Za-z]{2}", value):
        raise ValueError("must be a 2-letter state code")
    return value.upper()


def _zip(raw: Any) -> str:
    value = _text()(raw)
    if value is None:
        raise ValueError("is required")
    if not re.fullmatch(r"\d{5}", value):
        raise ValueError("must be a 5-digit zip")
    return value


def _ssn(raw: Any) -> str | None:
    value = _text()(raw)
    if value is None:
        return None
    # Formatting only; `ssn_format` (CQ-012) flags anything not 9 digits.
    return value.replace("-", "").replace(" ", "")


def _int(minimum: int = 0, maximum: int | None = None) -> Parser:
    def parse(raw: Any) -> int:
        if isinstance(raw, bool) or raw is None:
            raise ValueError("must be a whole number")
        try:
            value = int(str(raw))
        except ValueError as exc:
            raise ValueError("must be a whole number") from exc
        if value < minimum or (maximum is not None and value > maximum):
            upper = f"-{maximum}" if maximum is not None else "+"
            raise ValueError(f"must be in {minimum}{upper}")
        return value

    return parse


def _bool(raw: Any) -> bool:
    if not isinstance(raw, bool):
        raise ValueError("must be true or false")
    return raw


def _date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise ValueError("must be a date (YYYY-MM-DD)") from exc


def _money(raw: Any) -> Decimal:
    if isinstance(raw, bool) or raw is None:
        raise ValueError("must be an amount")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError("must be an amount") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("must be zero or more")
    return value.quantize(Decimal("0.01"))


def _opt_money(raw: Any) -> Decimal | None:
    return None if raw is None or raw == "" else _money(raw)


def _enum[E: enum.Enum](cls: type[E], nullable: bool = True) -> Parser:
    def parse(raw: Any) -> E | None:
        if raw is None or raw == "":
            if nullable:
                return None
            raise ValueError("is required")
        try:
            return cls(str(raw).strip().lower())
        except ValueError as exc:
            allowed = ", ".join(str(m.value) for m in cls)
            raise ValueError(f"must be one of {allowed}") from exc

    return parse


# --- loaders (revert) -------------------------------------------------------
# A revert restores the stored original exactly: loaders convert JSON back
# to the column's type (ISO date -> date, str -> Decimal / enum) and never
# normalise (review minor 1), unlike the edit parsers above.


def _as_is(raw: Any) -> Any:
    return raw


def _load_date(raw: Any) -> date | None:
    return None if raw is None else date.fromisoformat(str(raw))


def _load_money(raw: Any) -> Decimal | None:
    return None if raw is None else Decimal(str(raw))


def _load_enum[E: enum.Enum](cls: type[E]) -> Parser:
    def load(raw: Any) -> E | None:
        return None if raw is None else cls(raw)

    return load


def to_json(value: Any) -> Any:
    """Domain value -> JSON-safe value (Decimal and date as strings)."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


# --- registry --------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    attr: str
    label: str
    parse: Parser
    sensitive: bool = False
    load: Parser = _as_is
    """Stored original (JSON) -> column value, used by revert."""


def _enum_column(attr: str, label: str, cls: type[enum.Enum], nullable: bool = True) -> Column:
    return Column(attr, label, _enum(cls, nullable), load=_load_enum(cls))


def _money_column(attr: str, label: str, parse: Parser = _money) -> Column:
    return Column(attr, label, parse, load=_load_money)


APPLICATION_FIELDS: dict[str, Column] = {
    "occupancy_type": _enum_column("occupancy", "Occupancy", Occupancy),
    "investment_strategy": _enum_column("strategy", "Investment strategy", Strategy),
}

PARTY_COLUMNS: dict[str, Column] = {
    "first_name": Column("first_name", "First name", _text(required=True)),
    "last_name": Column("last_name", "Last name", _text(required=True)),
    "ssn": Column("ssn_encrypted", "SSN", _ssn, sensitive=True),
    "dob": Column("dob", "Date of birth", _date, sensitive=True, load=_load_date),
    "marital_status": _enum_column("marital_status", "Marital status", MaritalStatus),
    "dependents_count": Column("dependents_count", "Dependents", _int(0, 20)),
    "email": Column("email", "Email", _text()),
    "cell_phone": Column("cell_phone", "Cell phone", _text()),
    "home_phone": Column("home_phone", "Home phone", _text()),
    "work_phone": Column("work_phone", "Work phone", _text()),
    "business_vesting": _enum_column("business_vesting", "Vesting", BusinessVesting),
    "llc_entity_name": Column("llc_entity_name", "LLC name", _text()),
    "no_co_applicant_check": Column("no_co_applicant_check", "No co-applicant", _bool),
}

ROW_COLUMNS: dict[str, dict[str, Column]] = {
    "housing_history": {
        "street_address": Column("street_address", "Street address", _text(required=True)),
        "city": Column("city", "City", _text(required=True)),
        "state": Column("state", "State", _state),
        "zip": Column("zip", "Zip", _zip),
        "housing_status": _enum_column(
            "housing_status", "Own / rent", HousingStatus, nullable=False
        ),
        "residence_years": Column("residence_years", "Years at address", _int(0, 80)),
        "residence_months": Column("residence_months", "Months at address", _int(0, 11)),
        "vom_completed": Column("vom_completed", "VOM completed", _bool),
    },
    "liabilities": {
        "creditor_name": Column("creditor_name", "Creditor", _text(required=True)),
        "account_type": Column("account_type", "Account type", _text(required=True)),
        "monthly_payment": _money_column("monthly_payment", "Monthly payment"),
        "balance": _money_column("balance", "Balance"),
    },
    "assets": {
        "account_type": Column("account_type", "Account type", _text()),
        "institution": Column("institution", "Institution", _text()),
        "verified_amount": _money_column("verified_amount", "Verified amount"),
    },
    "employment": {
        "employer_name": Column("employer_name", "Employer", _text()),
        "monthly_income": _money_column("monthly_income", "Monthly income", _opt_money),
        "self_employed": Column("self_employed", "Self-employed", _bool),
    },
}

ROW_MODELS: dict[str, type[HousingHistory | Liability | Asset | Employment]] = {
    "housing_history": HousingHistory,
    "liabilities": Liability,
    "assets": Asset,
    "employment": Employment,
}

ROW_TABS: dict[str, ApplicationTab] = {
    "housing_history": ApplicationTab.HOUSING,
    "liabilities": ApplicationTab.CREDIT,
    "assets": ApplicationTab.ASSETS,
    "employment": ApplicationTab.ASSETS,
}

# Pricing keys stay on `/field-values` (plan.md #2).
PRICING_FIELD_KEYS = frozenset(
    {
        "property_tax_annual_rate",
        "homeowners_ins_annual",
        "hoa_fee_monthly",
        "market_rent_ltr",
        "gross_annual_revenue_str",
    }
)

_PARTY_KEY = re.compile(r"^(borrower|co_borrower)_([a-z_]+)$")
_ROW_KEY = re.compile(r"^([a-z_]+)\.([0-9a-f-]{36})\.([a-z_]+)$")


def party_field_key(role: PartyRole, column: str) -> str:
    return f"{role.value}_{column}"


def row_field_key(collection: str, row_id: uuid.UUID, column: str) -> str:
    return f"{collection}.{row_id}.{column}"


def base_source(application: Application) -> FieldSource:
    """Source of a value nobody edited (plan.md #21)."""
    if application.source is ApplicationSource.PORTAL:
        return FieldSource.DEFAULT
    return FieldSource.ENCOMPASS


@dataclass
class ResolvedField:
    field_key: str
    target: Any
    column: Column
    tab: ApplicationTab
    manual_row: bool = False
    party: ApplicationParty | None = None


async def _party_by_role(
    db: AsyncSession, application_id: uuid.UUID, role: PartyRole
) -> ApplicationParty | None:
    return (
        await db.execute(
            select(ApplicationParty).where(
                ApplicationParty.application_id == application_id,
                ApplicationParty.role == role,
            )
        )
    ).scalar_one_or_none()


async def resolve_field(
    db: AsyncSession, application: Application, field_key: str
) -> ResolvedField:
    """Maps a field key to the domain object + column it edits. 422 for an
    unknown key, 404 when the party/row does not exist on this application."""
    if field_key in PRICING_FIELD_KEYS:
        raise ValidationAppError(
            f"{field_key} is a pricing field; use PATCH /field-values/{field_key}."
        )
    if field_key in APPLICATION_FIELDS:
        return ResolvedField(
            field_key, application, APPLICATION_FIELDS[field_key], ApplicationTab.PROPERTY
        )

    party_match = _PARTY_KEY.match(field_key)
    if party_match and party_match.group(2) in PARTY_COLUMNS:
        role = PartyRole(party_match.group(1))
        party = await _party_by_role(db, application.id, role)
        if party is None:
            raise NotFoundError(f"No {role.value.replace('_', '-')} on this application.")
        manual = provenance.row_marker_key(
            "parties", party.id
        ) in await provenance.load_manual_rows(db, application.id)
        return ResolvedField(
            field_key,
            party,
            PARTY_COLUMNS[party_match.group(2)],
            ApplicationTab.BORROWERS,
            manual_row=manual,
            party=party,
        )

    row_match = _ROW_KEY.match(field_key)
    if row_match:
        collection, raw_id, column = row_match.groups()
        columns = ROW_COLUMNS.get(collection)
        if columns is not None and column in columns:
            row_id = uuid.UUID(raw_id)
            model = ROW_MODELS[collection]
            row: HousingHistory | Liability | Asset | Employment | None = await db.get(
                model, row_id
            )
            if row is None or row.application_id != application.id:
                raise NotFoundError(f"No {collection} row {row_id} on this application.")
            manual = provenance.row_marker_key(
                collection, row_id
            ) in await provenance.load_manual_rows(db, application.id)
            return ResolvedField(
                field_key, row, columns[column], ROW_TABS[collection], manual_row=manual
            )

    raise ValidationAppError(f"Unknown or read-only field: {field_key}")


def _payload(resolved: ResolvedField, old: Any, new: Any, message: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "field_key": resolved.field_key,
        "label": resolved.column.label,
        "message": message,
    }
    if resolved.column.sensitive:
        if resolved.column.attr == "ssn_encrypted":
            payload["from"] = mask_ssn(old)
            payload["to"] = mask_ssn(new)
    else:
        payload["from"] = to_json(old)
        payload["to"] = to_json(new)
    return payload


async def _home_phone_is_auto_copied(
    db: AsyncSession, application_id: uuid.UUID, party: ApplicationParty
) -> bool:
    """AC3 (plan.md #5, review minor 3): `phone_copy` filled the home phone
    (its `auto:` marker exists) and the LO has not typed one over it since
    (no `orig:` override). An LOS home phone that merely equals the cell
    phone has no marker, so it stays put."""
    if party.home_phone is None:
        return False
    key = party_field_key(party.role, "home_phone")
    if not await provenance.has_auto_marker(db, application_id, key):
        return False
    return await provenance.get_override(db, application_id, key) is None


async def _couple_strategy(
    db: AsyncSession, application: Application, occupancy: Any, user_id: uuid.UUID
) -> None:
    """Primary loans carry no strategy: setting occupancy to primary clears it
    (keeping the original in provenance, with an event); setting it back to
    investment restores a strategy that was cleared that way."""
    key = "investment_strategy"
    column = APPLICATION_FIELDS[key]
    if occupancy is Occupancy.PRIMARY and application.strategy is not None:
        old = application.strategy
        await provenance.record_override(
            db,
            application.id,
            key,
            original_value=to_json(old),
            original_source=base_source(application),
            user_id=user_id,
        )
        application.strategy = None
        events.add_event(
            db,
            application.id,
            actor=events.actor_for(user_id),
            type=events.FIELD_EDITED,
            payload={
                "field_key": key,
                "label": column.label,
                "from": to_json(old),
                "to": None,
                "message": "Cleared Investment strategy (primary occupancy)",
            },
        )
    elif occupancy is Occupancy.INVESTMENT and application.strategy is None:
        override = await provenance.get_override(db, application.id, key)
        if override is not None and override.value is not None:
            application.strategy = column.load(override.value)
            restored = override.value
            await db.delete(override)
            events.add_event(
                db,
                application.id,
                actor=events.actor_for(user_id),
                type=events.FIELD_REVERTED,
                payload={
                    "field_key": key,
                    "label": column.label,
                    "from": None,
                    "to": restored,
                    "message": "Restored Investment strategy (investment occupancy)",
                },
            )


async def _set_value(
    db: AsyncSession,
    application: Application,
    resolved: ResolvedField,
    new: Any,
    user_id: uuid.UUID,
) -> None:
    """Writes the column, applying the side rules: cell -> auto-copied home
    phone (AC3), and occupancy <-> strategy coupling."""
    old = getattr(resolved.target, resolved.column.attr)
    party = resolved.party
    if (
        party is not None
        and resolved.column.attr == "cell_phone"
        and await _home_phone_is_auto_copied(db, application.id, party)
    ):
        party.home_phone = new
        events.add_event(
            db,
            application.id,
            actor=events.SYSTEM_ACTOR,
            type=events.FIELD_AUTO_UPDATED,
            payload={
                "field_key": party_field_key(party.role, "home_phone"),
                "label": "Home phone",
                "from": old,
                "to": new,
                "message": "Home phone follows the cell phone (auto-copied)",
            },
        )
    setattr(resolved.target, resolved.column.attr, new)
    if resolved.target is application and resolved.column.attr == "occupancy":
        await _couple_strategy(db, application, new, user_id)


async def apply_field_edit(
    db: AsyncSession,
    application: Application,
    field_key: str,
    raw_value: Any,
    user_id: uuid.UUID,
) -> ResolvedField:
    """Validates and writes one field edit + its provenance + event. Does not
    commit. Unchanged values are a no-op (no event)."""
    resolved = await resolve_field(db, application, field_key)
    try:
        new = resolved.column.parse(raw_value)
    except ValueError as exc:
        raise _bad(resolved.column.label, str(exc)) from exc
    if (
        field_key == "investment_strategy"
        and new is not None
        and application.occupancy is Occupancy.PRIMARY
    ):
        raise ValidationAppError("Investment strategy applies to investment loans only.")
    party = resolved.party
    if (
        party is not None
        and party.role is PartyRole.BORROWER
        and resolved.column.attr == "home_phone"
        and new is None
        and party.cell_phone
    ):
        # Review minor 2 (plan.md #24): `phone_copy` would refill it from the
        # cell phone on the next verify, so an empty value cannot stick.
        raise _bad(
            resolved.column.label,
            "cannot be empty while a cell phone is on file (it is copied from the cell phone)",
        )
    old = getattr(resolved.target, resolved.column.attr)
    if new == old:
        return resolved

    if not resolved.manual_row:
        original = to_json(old)
        await provenance.record_override(
            db,
            application.id,
            field_key,
            original_value=provenance.seal(original) if resolved.column.sensitive else original,
            original_source=base_source(application),
            user_id=user_id,
        )
    await _set_value(db, application, resolved, new, user_id)
    events.add_event(
        db,
        application.id,
        actor=events.actor_for(user_id),
        type=events.FIELD_EDITED,
        payload=_payload(resolved, old, new, f"Edited {resolved.column.label}"),
    )
    await db.flush()
    return resolved


async def revert_field(
    db: AsyncSession, application: Application, field_key: str, user_id: uuid.UUID
) -> ResolvedField:
    """Restores the original value and drops the `orig:` row. 404 when the
    field was never overridden. Does not commit."""
    resolved = await resolve_field(db, application, field_key)
    override = await provenance.get_override(db, application.id, field_key)
    if override is None:
        raise NotFoundError(f"{resolved.column.label} has no LO edit to revert.")
    stored = provenance.unseal(override.value) if resolved.column.sensitive else override.value
    # Exact restore (review minor 1): type conversion only, no normalising.
    original = resolved.column.load(stored)
    old = getattr(resolved.target, resolved.column.attr)
    await db.delete(override)
    await db.flush()
    await _set_value(db, application, resolved, original, user_id)
    events.add_event(
        db,
        application.id,
        actor=events.actor_for(user_id),
        type=events.FIELD_REVERTED,
        payload=_payload(resolved, old, original, f"Reverted {resolved.column.label} to source"),
    )
    await db.flush()
    return resolved
