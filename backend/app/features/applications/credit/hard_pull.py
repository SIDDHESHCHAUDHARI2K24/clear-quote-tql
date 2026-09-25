"""The consent-gated hard credit pull (CQ-033).

`perform_hard_pull` is the only code path that asks the credit bureau for a
hard pull. It refuses -- raises, logs, writes nothing -- unless an
`accepted` `hard_pull` consent exists for the application (AC2); the check
lives here, not only in the portal UI or router.

On success it (plan.md decisions 3-5, 13):
1. pulls `CreditPullType.HARD_PULL` for the application's credit key (the
   LOS loan number, or `portal_credit_key` for a portal application, E14);
2. writes `representative_fico` = the middle of three scores and
   `credit_pull_type = Hard_Pull`, both `source_ref="hard_pull"` (the
   CQ-028a Credit-section contract);
3. refreshes tradelines into liabilities, never touching LO-added or
   LO-edited rows;
4. re-runs the verification rules (`run_and_persist`, same transaction);
5. marks the application's quotes stale if the FICO bracket changed (E12);
6. writes a `credit.hard_pull_completed` activity event.

Nothing here commits; the caller owns the transaction (and should hold
`lock_application`).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.enums import FieldSource
from app.core.errors import ConflictError, NotFoundError
from app.features.applications.credit.models import Liability
from app.features.applications.models import Application
from app.features.applications.sections import events, provenance
from app.features.applications.sections.service import fico_bracket
from app.features.applications.verification.models import FieldValue
from app.features.applications.verification.service import run_and_persist
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.quotes.stale.service import mark_application_quotes_stale
from app.integrations.credit.mock import MockCreditClient, portal_credit_key
from app.integrations.credit.models import CreditPullType
from app.integrations.credit.protocol import CreditClient

logger = logging.getLogger(__name__)

HARD_PULL_SOURCE_REF = "hard_pull"
HARD_PULL_TYPE_VALUE = "Hard_Pull"
HARD_PULL_COMPLETED = "credit.hard_pull_completed"
_ZERO = Decimal("0.00")


class HardPullConsentRequiredError(ConflictError):
    code = "HARD_PULL_CONSENT_REQUIRED"


@dataclass(frozen=True)
class HardPullResult:
    fico: int
    previous_fico: int | None
    bracket: str | None
    previous_bracket: str | None
    quotes_marked_stale: int
    liabilities_updated: int
    liabilities_added: int


def credit_key(application: Application) -> str:
    """The bureau key: the LOS loan number, else the portal key (E14)."""
    return application.los_loan_guid or portal_credit_key(application.id)


async def has_accepted_consent(db: AsyncSession, application_id: uuid.UUID) -> bool:
    found = (
        await db.execute(
            select(Consent.id)
            .where(
                Consent.application_id == application_id,
                Consent.type == ConsentType.HARD_PULL,
                Consent.status == ConsentStatus.ACCEPTED,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def _upsert_field(
    db: AsyncSession, application_id: uuid.UUID, field_key: str, value: Any
) -> None:
    stmt = insert(FieldValue).values(
        id=uuid.uuid4(),
        application_id=application_id,
        field_key=field_key,
        value=value,
        source=FieldSource.CREDIT_BUREAU,
        source_ref=HARD_PULL_SOURCE_REF,
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["application_id", "field_key"],
            set_={
                "value": stmt.excluded.value,
                "source": stmt.excluded.source,
                "source_ref": stmt.excluded.source_ref,
                "overridden_by": None,
                "overridden_at": None,
                "updated_at": now(),
            },
        )
    )


async def _current_fico(db: AsyncSession, application_id: uuid.UUID) -> int | None:
    value = (
        await db.execute(
            select(FieldValue.value).where(
                FieldValue.application_id == application_id,
                FieldValue.field_key == "representative_fico",
            )
        )
    ).scalar_one_or_none()
    try:
        return int(str(value)) if value is not None else None
    except ValueError:
        return None


def _amount(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


async def _refresh_liabilities(
    db: AsyncSession, application_id: uuid.UUID, tradelines: Any
) -> tuple[int, int]:
    """Upserts tradelines into liabilities (plan.md decision 4). Returns
    (updated, added)."""
    if not isinstance(tradelines, list) or not tradelines:
        return 0, 0
    manual = await provenance.load_manual_rows(db, application_id)
    overrides = await provenance.load_overrides(db, application_id)
    rows = (
        (await db.execute(select(Liability).where(Liability.application_id == application_id)))
        .scalars()
        .all()
    )

    def _protected(row: Liability) -> bool:
        if provenance.row_marker_key("liabilities", row.id) in manual:
            return True
        prefix = f"liabilities.{row.id}."
        return any(key.startswith(prefix) for key in overrides)

    candidates = {
        (_norm(row.creditor_name), _norm(row.account_type)): row
        for row in rows
        if not _protected(row)
    }
    protected_keys = {
        (_norm(row.creditor_name), _norm(row.account_type)) for row in rows if _protected(row)
    }
    updated = added = 0
    for line in tradelines:
        if not isinstance(line, dict):
            continue
        creditor = line.get("creditor") or line.get("creditor_name")
        account_type = line.get("type") or line.get("account_type") or "Other"
        if not creditor:
            continue
        key = (_norm(creditor), _norm(account_type))
        payment = _amount(line.get("monthly_payment"))
        balance = _amount(line.get("balance"))
        row = candidates.get(key)
        if row is not None:
            changed = False
            if payment is not None and payment != row.monthly_payment:
                row.monthly_payment = payment
                changed = True
            if balance is not None and balance != row.balance:
                row.balance = balance
                changed = True
            updated += int(changed)
            continue
        if key in protected_keys:
            # The LO already maintains this account by hand; leave it.
            continue
        new_row = Liability(
            application_id=application_id,
            creditor_name=str(creditor),
            account_type=str(account_type),
            monthly_payment=payment if payment is not None else _ZERO,
            balance=balance if balance is not None else _ZERO,
        )
        db.add(new_row)
        candidates[key] = new_row
        added += 1
    await db.flush()
    return updated, added


async def perform_hard_pull(
    db: AsyncSession,
    application_id: uuid.UUID,
    *,
    credit_client: CreditClient | None = None,
) -> HardPullResult:
    """Runs the hard pull for `application_id`; see the module docstring.

    Raises `HardPullConsentRequiredError` (409) before any provider call or
    write unless an accepted `hard_pull` consent exists (AC2)."""
    if not await has_accepted_consent(db, application_id):
        logger.warning(
            "Refused hard pull for application %s: no accepted hard_pull consent",
            application_id,
        )
        raise HardPullConsentRequiredError(
            "A hard credit pull needs the borrower's accepted consent first."
        )
    application = await db.get(Application, application_id)
    if application is None:
        raise NotFoundError("Application not found.")

    client = credit_client if credit_client is not None else MockCreditClient(db)
    report = await client.pull_credit(credit_key(application), CreditPullType.HARD_PULL)
    fico = int(report.middle_score)

    previous_fico = await _current_fico(db, application_id)
    await _upsert_field(db, application_id, "representative_fico", fico)
    await _upsert_field(db, application_id, "credit_pull_type", HARD_PULL_TYPE_VALUE)
    updated, added = await _refresh_liabilities(db, application_id, report.tradelines)

    await run_and_persist(application_id, db, commit=False)

    previous_bracket = fico_bracket(previous_fico)
    bracket = fico_bracket(fico)
    stale = 0
    if previous_bracket != bracket:
        reason = f"fico_bucket_change {previous_bracket or 'none'} -> {bracket}"
        logger.info(
            "Hard pull for application %s crossed a FICO bucket: %s", application_id, reason
        )
        stale = await mark_application_quotes_stale(db, application_id, reason)

    events.add_event(
        db,
        application_id,
        actor=events.SYSTEM_ACTOR,
        type=HARD_PULL_COMPLETED,
        payload={
            "field_key": "representative_fico",
            "fico": fico,
            "previous_fico": previous_fico,
            "bracket": bracket,
            "previous_bracket": previous_bracket,
            "quotes_marked_stale": stale,
            "liabilities_updated": updated,
            "liabilities_added": added,
            "message": f"Hard credit pull complete — FICO {fico}",
        },
    )
    await db.flush()
    return HardPullResult(
        fico=fico,
        previous_fico=previous_fico,
        bracket=bracket,
        previous_bracket=previous_bracket,
        quotes_marked_stale=stale,
        liabilities_updated=updated,
        liabilities_added=added,
    )
