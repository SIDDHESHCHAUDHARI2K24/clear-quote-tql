"""Reads `seed/personas/*.yaml`, `seed/providers/*.yaml` and `seed/users.yaml`
and drives every persona through the same stage service functions CQ-011's
workflow will later wrap as activities, in the same order (Decision D1,
plan.md) -- `applications.service.import_from_los` (CQ-010, this item) then
`applications.verification.service.run_and_persist` (CQ-012), then the
pricing seam (`seed/pricing_seam.py`, CQ-013's real, merged functions).

Every dollar/rate figure this module writes for a priced quote comes from
`quote_engine` (via CQ-013's `auto_price`) or is a raw input the persona
table pins (price, down %, FICO, etc.) -- nothing here hand-types a computed
number, per spec.md scope item 8.

Review round 1 (orchestrator decisions): `applications.occupancy` and
`field_values.representative_fico` are now both written by
`applications.service.import_from_los` itself (copied from the LOS record's
`occupancy_type`, and a real soft credit pull, respectively) -- this module
no longer seeds either one directly. Persona 7 (Aisha Coleman)'s LOS record
has no `occupancy_type`, so `import_from_los` leaves her `occupancy` `NULL`
and the pipeline's Validate stage (`seed/pricing_seam.py` ->
`validate_ob_required_fields`) raises "Cannot price: missing Occupancy" as
system-design.md/spec.md/CQ-012's spec.md all pin it -- no seed-side
special-casing needed any more.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import bcrypt
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import (
    ApplicationStatus,
    FlagSeverity,
    Strategy,
    UserRole,
)
from app.core.errors import AppError
from app.features.applications.models import Application, BusinessVesting
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.applications.service import import_from_los
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.service import run_and_persist
from app.features.auth.models import User
from app.features.clients.models import Client
from app.features.notifications.outbox.models import EmailStatus, OutboxEmail
from app.features.quotes.send.models import BorrowerAction, QuotePackage
from app.integrations.credit.models import CreditPullType, ProviderCreditReport
from app.integrations.insurance.models import ProviderInsuranceFactor
from app.integrations.los.models import ProviderLosRecord
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram
from app.integrations.property_search.models import DealGrade, ProviderListing
from app.integrations.rent.models import ProviderRent
from app.integrations.str.models import ProviderStrRevenue
from app.integrations.tax.models import ProviderTaxRate
from seed.generators.documents import (
    generate_sample_pdf,
    generate_sample_png,
    upload_sample_document,
)
from seed.pricing_seam import run_pricing_stage

SEED_ROOT = Path(__file__).resolve().parent
PERSONAS_DIR = SEED_ROOT / "personas"
PROVIDERS_DIR = SEED_ROOT / "providers"
USERS_FIXTURE = SEED_ROOT / "users.yaml"

_PROPERTY_TYPE_MAP: dict[str, PropertyType] = {
    "single_family": PropertyType.SINGLE_FAMILY,
    "two_to_four_unit": PropertyType.TWO_TO_FOUR_UNIT,
    "condo": PropertyType.CONDO,
    "townhome": PropertyType.TOWNHOME,
}
_VESTING_MAP: dict[str, BusinessVesting] = {
    "personal_name": BusinessVesting.PERSONAL_NAME,
    "title_lien_in_llc": BusinessVesting.TITLE_LIEN_IN_LLC,
}


def load_persona_fixtures() -> list[dict[str, Any]]:
    return [yaml.safe_load(path.read_text()) for path in sorted(PERSONAS_DIR.glob("*.yaml"))]


def load_provider_fixture(name: str) -> list[dict[str, Any]]:
    return yaml.safe_load((PROVIDERS_DIR / name).read_text()) or []


def load_users_fixture() -> list[dict[str, Any]]:
    return yaml.safe_load(USERS_FIXTURE.read_text())


# --- Users ---------------------------------------------------------------


@dataclass
class UserSeedResult:
    by_key: dict[str, uuid.UUID] = field(default_factory=dict)
    lo_ids: list[uuid.UUID] = field(default_factory=list)


class MissingStaffPasswordError(RuntimeError):
    """Raised when `SEED_STAFF_PASSWORD` is unset -- review round 1, finding
    #3: no plaintext staff password is ever committed to the repo, so
    `seed_users` has nothing to hash without this env var."""


def _staff_password() -> str:
    # Read via `get_settings()` (pydantic-settings), not a raw
    # `os.environ.get` -- `Settings.model_config` loads `.env` itself, which
    # is how every other seed/dev knob (`DEV_LO_ID`, `S3_*`, ...) already
    # reaches this process; a bare `os.environ` read would miss a value set
    # only in `.env` and never exported into the shell.
    password = get_settings().seed_staff_password
    if not password:
        raise MissingStaffPasswordError(
            "SEED_STAFF_PASSWORD is not set. `make demo-reset` needs a demo "
            "password to bcrypt-hash for the seeded staff users (2 LO, 1 "
            "Manager, 1 Admin) -- set it in your .env (see .env.example) "
            "before running `make demo-reset` again."
        )
    return password


async def seed_users(db: AsyncSession) -> UserSeedResult:
    """AC4: exactly 2 LO, 1 Manager, 1 Admin, each with a bcrypt hash of the
    shared demo password read from `SEED_STAFF_PASSWORD` (review round 1,
    finding #3 -- no plaintext password is committed to the repo)."""
    password_hash = bcrypt.hashpw(_staff_password().encode("utf-8"), bcrypt.gensalt()).decode(
        "ascii"
    )
    result = UserSeedResult()
    for row in load_users_fixture():
        user = User(
            id=uuid.UUID(row["id"]) if row.get("id") else uuid.uuid4(),
            email=row["email"],
            password_hash=password_hash,
            role=UserRole(row["role"]),
            full_name=row["full_name"],
            nmls=row.get("nmls"),
            title=row.get("title"),
            phone=row.get("phone"),
        )
        db.add(user)
        await db.flush()
        result.by_key[row["key"]] = user.id
        if user.role is UserRole.LO:
            result.lo_ids.append(user.id)
    await db.commit()
    return result


# --- Providers -------------------------------------------------------------


async def seed_providers(db: AsyncSession) -> None:
    """AC3: at least one row per persona market in each of the 5 named
    `provider_*` tables, plus credit/insurance rows so every mock adapter
    (not just the 5 AC3 names) returns non-empty for every persona."""
    for row in load_provider_fixture("tax_rates.yaml"):
        db.add(
            ProviderTaxRate(
                county=row["county"],
                state=row["state"],
                annual_rate_pct=Decimal(str(row["annual_rate_pct"])),
                source_name=row["source_name"],
                as_of=date.fromisoformat(row["as_of"]),
            )
        )
    for row in load_provider_fixture("rents.yaml"):
        db.add(
            ProviderRent(
                zip=row["zip"],
                beds=row["beds"],
                market_rent=Decimal(str(row["market_rent"])),
                rent_low=Decimal(str(row["rent_low"])),
                rent_high=Decimal(str(row["rent_high"])),
                comps_count=row["comps_count"],
                as_of=date.fromisoformat(row["as_of"]),
            )
        )
    for row in load_provider_fixture("str_revenue.yaml"):
        db.add(
            ProviderStrRevenue(
                zip=row["zip"],
                beds=row["beds"],
                annual_revenue=Decimal(str(row["annual_revenue"])),
                occupancy_pct=Decimal(str(row["occupancy_pct"])),
                adr=Decimal(str(row["adr"])),
                comps_count=row["comps_count"],
                as_of=date.fromisoformat(row["as_of"]),
            )
        )
    for row in load_provider_fixture("rate_sheet.yaml"):
        db.add(
            ProviderRateSheet(
                investor_name=row["investor_name"],
                product_name=row["product_name"],
                program=RateSheetProgram(row["program"]),
                base_rate=Decimal(str(row["base_rate"])),
                base_price=Decimal(str(row["base_price"])),
                min_fico=row["min_fico"],
                max_ltv=Decimal(str(row["max_ltv"])),
                dscr_bucket=row.get("dscr_bucket"),
                ppp_years=row.get("ppp_years"),
                str_only=bool(row.get("str_only", False)),
                lead_source=row.get("lead_source"),
                lock_days=row["lock_days"],
                fico_adjustment_bps=Decimal(str(row.get("fico_adjustment_bps", "0"))),
                ltv_adjustment_bps=Decimal(str(row.get("ltv_adjustment_bps", "0"))),
            )
        )
    for row in load_provider_fixture("listings.yaml"):
        db.add(
            ProviderListing(
                address=row["address"],
                city=row["city"],
                state=row["state"],
                zip=row["zip"],
                metro=row["metro"],
                list_price=Decimal(str(row["list_price"])),
                beds=row["beds"],
                baths=Decimal(str(row["baths"])),
                sqft=row["sqft"],
                property_type=_PROPERTY_TYPE_MAP[row["property_type"]],
                image_url=row["image_url"],
                deal_grade=DealGrade(row["deal_grade"]),
                tagline=row.get("tagline"),
            )
        )
    for row in load_provider_fixture("insurance_factors.yaml"):
        db.add(
            ProviderInsuranceFactor(
                state=row["state"],
                annual_rate_pct=Decimal(str(row["annual_rate_pct"])),
                source_name=row["source_name"],
            )
        )
    for row in load_provider_fixture("credit_reports.yaml"):
        db.add(
            ProviderCreditReport(
                loan_number=row["loan_number"],
                pull_type=CreditPullType(row["pull_type"]),
                experian_score=row.get("experian_score"),
                equifax_score=row.get("equifax_score"),
                transunion_score=row.get("transunion_score"),
                middle_score=row["middle_score"],
                tradelines=row.get("tradelines", []),
            )
        )
    await db.flush()
    await db.commit()


# --- Personas ----------------------------------------------------------------


@dataclass
class PersonaSeedResult:
    key: str
    application_id: uuid.UUID
    client_id: uuid.UUID
    final_status: ApplicationStatus
    pricing_ran: bool
    activity_event_types: list[str] = field(default_factory=list)


async def _add_activity_event(
    db: AsyncSession, application_id: uuid.UUID, event_type: str, payload: dict[str, Any]
) -> None:
    db.add(
        ActivityEvent(
            application_id=application_id,
            actor="system",
            type=event_type,
            payload=payload,
            at=datetime.now(UTC),
        )
    )
    await db.flush()
    await db.commit()


async def seed_persona(
    db: AsyncSession,
    persona: dict[str, Any],
    *,
    lo_id: uuid.UUID,
    s3_client: Any | None = None,
) -> PersonaSeedResult:
    """Creates the client/application/property/LOS-record rows, then runs
    Import -> Verify -> (pricing seam), writing one `activity_events` row per
    completed stage (mirrors CQ-011's `activity_events` types table, spec.md
    references)."""
    client = Client(
        full_name=f"{persona['first_name']} {persona['last_name']}",
        email=persona["email"],
        assigned_lo_id=lo_id,
    )
    db.add(client)
    await db.flush()

    # `strategy` (LTR/STR) is LO-entered at intake and stays that way -- no
    # persona's defect involves a missing `investment_strategy`, so it's
    # still set directly here. `occupancy` is intentionally left unset:
    # `import_from_los` (review round 1, finding #1) is now the sole source
    # of truth, copying it from the LOS record's `occupancy_type` -- `NULL`
    # for Aisha Coleman, whose record has none.
    strategy = Strategy(persona["strategy"]) if persona.get("strategy") else None

    application = Application(
        client_id=client.id,
        lo_id=lo_id,
        los_loan_guid=persona["loan_number"],
        status=ApplicationStatus.INTAKE,
        occupancy=None,
        strategy=strategy,
        requested_price=Decimal(str(persona["purchase_price"])),
        subject_state=persona["market"]["state"],
    )
    db.add(application)
    await db.flush()

    market = persona["market"]
    los_record_payload = persona["los_record"]
    is_tbd = los_record_payload.get("property_address_status") == "TBD"
    address_status = PropertyAddressStatus.TBD if is_tbd else PropertyAddressStatus.SPECIFIC_ADDRESS
    prop = Property(
        application_id=application.id,
        address_status=address_status,
        street_address=None if is_tbd else los_record_payload.get("subject_street_address"),
        city=market["city"],
        state=market["state"],
        zip=market["zip"],
        county=market["county"],
        property_type=_PROPERTY_TYPE_MAP[persona["property_type"]],
        number_of_units=1,
        buy_box_states=los_record_payload.get("buy_box_states") or [],
        buy_box_metros=los_record_payload.get("buy_box_market_cities") or [],
    )
    db.add(prop)

    db.add(ProviderLosRecord(loan_number=persona["loan_number"], payload=los_record_payload))
    await db.flush()
    await db.commit()

    activity_types: list[str] = []

    await import_from_los(application.id, db)
    await _add_activity_event(db, application.id, "pipeline.imported", {})
    activity_types.append("pipeline.imported")

    verification_result = await run_and_persist(application.id, db)
    has_blocking_flag = any(
        f.severity is FlagSeverity.BLOCKING for f in verification_result.flags_raised
    )
    await db.refresh(application)
    if has_blocking_flag:
        application.status = ApplicationStatus.NEEDS_ATTENTION
        event_type = "pipeline.flagged"
        payload = {"flags": [f.rule for f in verification_result.flags_raised]}
    else:
        application.status = ApplicationStatus.READY_TO_PRICE
        event_type = "pipeline.verified"
        payload = {}
    await db.flush()
    await db.commit()
    await _add_activity_event(db, application.id, event_type, payload)
    activity_types.append(event_type)

    pricing_ran = False
    if application.status is ApplicationStatus.READY_TO_PRICE:
        try:
            pricing_stage_result = await run_pricing_stage(db, application.id)
        except AppError as exc:
            await db.refresh(application)
            application.status = ApplicationStatus.NEEDS_ATTENTION
            await db.flush()
            await db.commit()
            await _add_activity_event(
                db, application.id, "pipeline.pricing_blocked", {"reason": exc.message}
            )
            activity_types.append("pipeline.pricing_blocked")
        else:
            pricing_ran = True
            await db.refresh(application)
            application.status = ApplicationStatus.PRICED
            await db.flush()
            await db.commit()
            await _add_activity_event(db, application.id, "pipeline.priced", {})
            activity_types.append("pipeline.priced")

            fixture_layer = persona.get("fixture_layer")
            if fixture_layer:
                quote_ids = pricing_stage_result.quote_set_result.quote_ids
                if quote_ids:
                    await apply_send_fixture(
                        db,
                        application_id=application.id,
                        quote_ids=list(quote_ids),
                        recommended_quote_id=quote_ids[0],
                        sent_days_ago=fixture_layer["sent_days_ago"],
                        viewed_days_ago=fixture_layer.get("viewed_days_ago"),
                        borrower_action=(
                            BorrowerAction.OPTION_SELECTED
                            if "viewed_days_ago" in fixture_layer
                            else None
                        ),
                        borrower_email=persona["email"],
                    )

    if s3_client is not None:
        await seed_persona_documents(db, s3_client, application.id, persona)

    await db.refresh(application)
    return PersonaSeedResult(
        key=persona["key"],
        application_id=application.id,
        client_id=client.id,
        final_status=application.status,
        pricing_ran=pricing_ran,
        activity_event_types=activity_types,
    )


async def seed_persona_documents(
    db: AsyncSession, s3_client: Any, application_id: uuid.UUID, persona: dict[str, Any]
) -> None:
    """AC6: at least one `documents` row per persona, pointing at a
    watermarked object in `clearquote-demo-docs`."""
    from app.features.applications.assets.models import Document

    pdf_bytes = generate_sample_pdf(f"{persona['first_name']} {persona['last_name']} -- Pay Stub")
    pdf_key = upload_sample_document(
        s3_client,
        application_id=application_id,
        doc_type="pay_stub",
        content=pdf_bytes,
        ext="pdf",
    )
    db.add(Document(application_id=application_id, doc_type="pay_stub", object_key=pdf_key))

    full_name = f"{persona['first_name']} {persona['last_name']}"
    png_bytes = generate_sample_png(f"{full_name} -- Bank Statement")
    png_key = upload_sample_document(
        s3_client,
        application_id=application_id,
        doc_type="bank_statement",
        content=png_bytes,
        ext="png",
    )
    db.add(Document(application_id=application_id, doc_type="bank_statement", object_key=png_key))
    await db.flush()
    await db.commit()


# --- Decision D2: post-pipeline fixture layer (Grace Kim, Luis Romero) ------


async def apply_send_fixture(
    db: AsyncSession,
    *,
    application_id: uuid.UUID,
    quote_ids: list[uuid.UUID],
    recommended_quote_id: uuid.UUID,
    sent_days_ago: int,
    viewed_days_ago: int | None,
    borrower_action: BorrowerAction | None,
    borrower_email: str,
) -> QuotePackage:
    """Writes the downstream rows features CQ-019/CQ-020/CQ-024 own writing
    at runtime -- `quote_packages`, one `activity_events` row per hop, and
    one `outbox_emails` row for the send (Decision D2, spec.md). The dollar
    figures inside `quote_ids`/`recommended_quote_id` are whatever
    `quote_engine`-backed `Quote` rows the caller already created (via the
    real pipeline in Phase B, or a test's own fixture) -- this function only
    authors status/timestamps, never a money figure.
    """
    now = datetime.now(UTC)
    sent_at = now - timedelta(days=sent_days_ago)
    viewed_at = now - timedelta(days=viewed_days_ago) if viewed_days_ago is not None else None

    package = QuotePackage(
        application_id=application_id,
        quote_ids=quote_ids,
        recommended_quote_id=recommended_quote_id,
        report_token=secrets.token_urlsafe(24),
        sent_at=sent_at,
        expires_at=sent_at + timedelta(days=7),
        viewed_at=viewed_at,
        borrower_action=borrower_action,
    )
    db.add(package)
    await db.flush()

    application = await db.get(Application, application_id)
    assert application is not None
    application.status = (
        ApplicationStatus.OPTION_SELECTED if borrower_action else ApplicationStatus.SENT
    )

    db.add(
        OutboxEmail(
            to_email=borrower_email,
            subject="Your Clear Quote pre-approval is ready",
            html=f"<p>Your report is ready: report_token={package.report_token}</p>",
            attachment_keys=[],
            status=EmailStatus.SENT,
            application_id=application_id,
        )
    )
    await db.flush()
    await _add_activity_event(db, application_id, "quote.sent", {"sent_at": sent_at.isoformat()})
    if viewed_at is not None:
        await _add_activity_event(
            db, application_id, "quote.viewed", {"viewed_at": viewed_at.isoformat()}
        )
    if borrower_action is BorrowerAction.OPTION_SELECTED:
        await _add_activity_event(
            db, application_id, "quote.option_selected", {"quote_id": str(recommended_quote_id)}
        )

    await db.commit()
    return package
