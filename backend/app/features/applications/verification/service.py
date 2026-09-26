"""Assembles a `VerificationContext` from the DB, calls `evaluate_rules`,
and persists the outcome — auto-fixes onto `application_parties`, failing
non-info results as `flags` rows (via `write_flag`), and resolving any
previously-raised flag whose rule now passes.

`run_and_persist` does **not** write `activity_events` rows: CQ-011 owns
exactly one `activity_events` row per completed pipeline stage (its own
spec.md AC5). It returns a `VerificationRunResult` instead, so the caller
(CQ-011's `verify_application` activity) can build whatever single
stage-level row it needs from the rule results, auto-fixes, and flags
raised/resolved (plan.md decision #11 — see spec.md line ~71, updated).

`write_flag` is the shared helper CQ-013's OB-required-field validation
stage also calls for persona 7 (Aisha Coleman) — see spec.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.enums import ApplicationTab, FieldSource, FlagSeverity, Occupancy
from app.features.applications.assets.models import Asset, Employment
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory
from app.features.applications.locking import lock_application
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.verification.models import FieldValue, Flag
from app.features.applications.verification.rules import evaluate_rules, flag_message
from app.features.applications.verification.schemas import (
    HousingSnapshot,
    PartySnapshot,
    RuleResult,
    ScenarioSnapshot,
    VerificationContext,
)
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.settings.models import Setting

# rule_id -> the `application_parties` attribute an auto-fixed RuleResult's
# `fix_value` gets written onto. Both of today's auto-fix rules only ever
# act on the primary (BORROWER-role) party (plan.md decision #7).
_AUTO_FIX_ATTR: dict[str, str] = {
    "phone_copy": "home_phone",
    "no_co_applicant": "no_co_applicant_check",
}

AUTO_PREFIX = "auto:"
"""`field_values` key prefix marking a value a rule copied automatically
(CQ-028a review): `auto:borrower_home_phone` means `phone_copy` filled the
home phone from the cell phone, so the verification tabs keep it following
the cell phone. Like CQ-028a's `orig:`/`row:` keys it contains `:`, which
no catalog key does."""


def auto_marker_key(field_key: str) -> str:
    return f"{AUTO_PREFIX}{field_key}"


async def mark_auto_copied(db: AsyncSession, application_id: uuid.UUID, field_key: str) -> None:
    """Idempotently writes the `auto:{field_key}` marker. Does not commit."""
    await db.execute(
        insert(FieldValue)
        .values(
            id=uuid.uuid4(),
            application_id=application_id,
            field_key=auto_marker_key(field_key),
            value=FieldSource.FORMULA.value,
            source=FieldSource.FORMULA,
        )
        .on_conflict_do_nothing(index_elements=["application_id", "field_key"])
    )


@dataclass
class VerificationRunResult:
    """Everything `run_and_persist` did, for the caller to log or act on —
    it deliberately holds no opinion about `activity_events` (plan.md
    decision #11): CQ-011 builds its own single stage-level row from this.
    """

    rule_results: list[RuleResult] = field(default_factory=list)
    """Every `RuleResult` `evaluate_rules` returned this run (skipped rules
    are simply absent, per `evaluate_rules`'s own contract)."""
    auto_fixed: list[RuleResult] = field(default_factory=list)
    """The subset of `rule_results` that actually changed an
    `application_parties` column this run (`auto_fixed=True` results where
    a fix value was applied — not every INFO-severity result, since e.g.
    `phone_copy` returns `auto_fixed=False` when nothing needed copying)."""
    flags_raised: list[Flag] = field(default_factory=list)
    """`flags` rows created or refreshed this run (still unresolved)."""
    flags_resolved: list[Flag] = field(default_factory=list)
    """Previously-unresolved `flags` rows whose rule passed this run and
    were therefore resolved."""


async def setting_int(db: AsyncSession, key: str) -> int:
    row = await db.get(Setting, key)
    if row is None:
        raise RuntimeError(f"Missing required setting: {key!r} (seed_settings_defaults not run?)")
    return int(row.value)  # type: ignore[arg-type]


async def latest_scenario_snapshot(
    db: AsyncSession, application_id: uuid.UUID
) -> ScenarioSnapshot | None:
    """Reads the application's most-recently-priced `Quote.computed` (CQ-008's
    `QuoteComputation`, stored as JSON) and maps its already-computed
    `cash_to_close`/`total_monthly_payment` onto `ScenarioSnapshot` — no new
    money math (plan.md decision #4)."""
    stmt = (
        select(Quote)
        .join(Scenario, Quote.scenario_id == Scenario.id)
        .where(Scenario.application_id == application_id)
        .order_by(Quote.priced_at.desc(), Quote.created_at.desc())
        .limit(1)
    )
    quote = (await db.execute(stmt)).scalars().first()
    if quote is None or not isinstance(quote.computed, dict):
        return None
    computed = quote.computed
    return ScenarioSnapshot(
        total_cash_to_close=Decimal(str(computed["cash_to_close"])),
        total_monthly_payment=Decimal(str(computed["total_monthly_payment"])),
    )


async def _build_context(db: AsyncSession, application: Application) -> VerificationContext:
    party_rows = (
        (
            await db.execute(
                select(ApplicationParty).where(ApplicationParty.application_id == application.id)
            )
        )
        .scalars()
        .all()
    )
    parties = [
        PartySnapshot(
            role=p.role,
            cell_phone=p.cell_phone,
            home_phone=p.home_phone,
            # `ssn_encrypted` decrypts transparently on read (EncryptedString
            # TypeDecorator) -- this is already plaintext (plan.md decision #2).
            ssn=p.ssn_encrypted,
            dob=p.dob,
        )
        for p in party_rows
    ]

    housing_rows = (
        (
            await db.execute(
                select(HousingHistory)
                .where(HousingHistory.application_id == application.id)
                .order_by(HousingHistory.sequence)
            )
        )
        .scalars()
        .all()
    )
    housing_history = [
        HousingSnapshot(
            sequence=h.sequence,
            residence_years=h.residence_years,
            residence_months=h.residence_months,
        )
        for h in housing_rows
    ]

    assets_total = (
        await db.execute(
            select(func.sum(Asset.verified_amount)).where(Asset.application_id == application.id)
        )
    ).scalar_one_or_none() or Decimal("0")
    liabilities_total = (
        await db.execute(
            select(func.sum(Liability.monthly_payment)).where(
                Liability.application_id == application.id
            )
        )
    ).scalar_one_or_none() or Decimal("0")
    monthly_income = (
        await db.execute(
            select(func.sum(Employment.monthly_income)).where(
                Employment.application_id == application.id
            )
        )
    ).scalar_one_or_none() or Decimal("0")

    reserves_key = (
        "reserves_months_primary"
        if application.occupancy is Occupancy.PRIMARY
        else "reserves_months_investment"
    )
    reserves_months = await setting_int(db, reserves_key)

    latest_scenario = await latest_scenario_snapshot(db, application.id)

    return VerificationContext(
        occupancy=application.occupancy,
        parties=parties,
        housing_history=housing_history,
        assets_total=Decimal(assets_total),
        liabilities_total=Decimal(liabilities_total),
        monthly_income=Decimal(monthly_income),
        reserves_months=reserves_months,
        latest_scenario=latest_scenario,
        as_of=clock.now().date(),
    )


async def write_flag(
    db: AsyncSession,
    application_id: uuid.UUID,
    tab: ApplicationTab,
    field_key: str,
    rule: str,
    severity: FlagSeverity,
    message: str | None = None,
) -> Flag:
    """Upserts a `flags` row: reuses the existing *unresolved* row for
    `(application_id, field_key, rule)` if one exists (refreshing its
    `tab`/`severity`/`message`), else creates one. Shared by this item's own
    rules and CQ-013's OB-required-field validation stage (persona 7, Aisha
    Coleman). `message` (P5/P6 foundation, E8) is the human-readable text;
    `None` falls back to `rules.flag_message(rule, field_key)`.
    Does not commit — the caller controls the transaction boundary.
    Takes the application row lock (CQ-028a review), so concurrent writers
    (rules, the pricing validator, the DSCR loop) never both insert.
    """
    await lock_application(db, application_id)
    text = message or flag_message(rule, field_key)
    existing = (
        await db.execute(
            select(Flag).where(
                Flag.application_id == application_id,
                Flag.field_key == field_key,
                Flag.rule == rule,
                Flag.resolved_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.tab = tab
        existing.severity = severity
        existing.message = text
        await db.flush()
        return existing

    flag = Flag(
        application_id=application_id,
        tab=tab,
        field_key=field_key,
        rule=rule,
        severity=severity,
        message=text,
    )
    db.add(flag)
    await db.flush()
    return flag


async def resolve_flag(
    db: AsyncSession, application_id: uuid.UUID, field_key: str, rule: str
) -> Flag | None:
    """Resolves (sets `resolved_at`) the existing unresolved `flags` row for
    `(application_id, field_key, rule)`, if one exists — supports the
    design's "LO fixes -> resume" loop (`NeedsAttention -> Verifying: LO
    resolves`, system-design.md) and CQ-028's tab flag counts. Returns
    `None` (a no-op) if no such row exists. Does not commit."""
    existing = (
        await db.execute(
            select(Flag).where(
                Flag.application_id == application_id,
                Flag.field_key == field_key,
                Flag.rule == rule,
                Flag.resolved_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return None
    existing.resolved_at = clock.now()
    await db.flush()
    return existing


async def run_and_persist(
    application_id: uuid.UUID, db: AsyncSession, *, commit: bool = True
) -> VerificationRunResult:
    """Assembles the application's `VerificationContext`, evaluates every
    rule, applies auto-fixes back onto `application_parties`, writes failing
    non-`info` results as `flags` rows, and resolves any previously-raised
    flag whose rule now passes. Commits once at the end. Does not write
    `activity_events` — see module docstring.

    Takes the application row lock first (CQ-028a review M1), so the
    pipeline's verify and the verification tabs' re-verify never race on
    `flags`. `commit=False` leaves the transaction (and the lock) open, so
    the pipeline's verify can set the status from these results before
    anyone else re-verifies."""
    await lock_application(db, application_id)
    application = await db.get(Application, application_id)
    if application is None:
        raise ValueError(f"No application with id {application_id}")

    context = await _build_context(db, application)
    results = evaluate_rules(context)

    primary_party = (
        await db.execute(
            select(ApplicationParty).where(
                ApplicationParty.application_id == application_id,
                ApplicationParty.role == PartyRole.BORROWER,
            )
        )
    ).scalar_one_or_none()

    run_result = VerificationRunResult(rule_results=results)

    for result in results:
        if result.auto_fixed:
            attr = _AUTO_FIX_ATTR.get(result.rule_id)
            if attr is not None and primary_party is not None:
                setattr(primary_party, attr, result.fix_value)
                if result.rule_id == "phone_copy":
                    await mark_auto_copied(db, application_id, result.field_key)
                run_result.auto_fixed.append(result)
        elif result.severity is not FlagSeverity.INFO:
            if not result.passed:
                flag = await write_flag(
                    db,
                    application_id,
                    result.tab,
                    result.field_key,
                    result.rule_id,
                    result.severity,
                    message=result.message,
                )
                run_result.flags_raised.append(flag)
            else:
                resolved = await resolve_flag(db, application_id, result.field_key, result.rule_id)
                if resolved is not None:
                    run_result.flags_resolved.append(resolved)

    await db.flush()
    if commit:
        await db.commit()
    return run_result
