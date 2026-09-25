"""CQ-033 AC2 and AC4: the consent-gated hard-pull service, called directly
on the seeded Tom & Lisa Brandt persona (priced, with quotes)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from seed.loader import load_persona_fixtures, seed_persona, seed_providers, seed_users
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.features.applications.credit.hard_pull import (
    HardPullConsentRequiredError,
    perform_hard_pull,
)
from app.features.applications.credit.models import Liability
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.integrations.common.models import IntegrationCall
from app.integrations.credit.models import CreditPullType, ProviderCreditReport


async def _seed_brandt(db: AsyncSession) -> Application:
    users = await seed_users(db)
    await seed_providers(db)
    persona = next(p for p in load_persona_fixtures() if p["key"] == "tom_lisa_brandt")
    result = await seed_persona(db, persona, lo_id=users.lo_ids[0], s3_client=None)
    application = await db.get(Application, result.application_id)
    assert application is not None
    return application


async def _accept(db: AsyncSession, application_id: uuid.UUID) -> None:
    db.add(
        Consent(
            application_id=application_id,
            type=ConsentType.HARD_PULL,
            status=ConsentStatus.ACCEPTED,
            requested_at=now(),
            decided_at=now(),
            at=now(),
        )
    )
    await db.flush()


async def _field(db: AsyncSession, application_id: uuid.UUID, key: str) -> FieldValue | None:
    return (
        await db.execute(
            select(FieldValue)
            .where(FieldValue.application_id == application_id, FieldValue.field_key == key)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _quotes_stale(db: AsyncSession, application_id: uuid.UUID) -> list[bool]:
    rows = await db.execute(
        select(Quote.stale)
        .join(Scenario, Quote.scenario_id == Scenario.id)
        .where(Scenario.application_id == application_id)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _count(db: AsyncSession, stmt: Any) -> int:
    return int((await db.execute(stmt)).scalar_one())


async def test_hard_pull_requires_consent(db_session: AsyncSession) -> None:
    """AC2: no accepted consent -> raises, writes nothing (no FICO change,
    no liabilities change, no event, no provider call)."""
    app = await _seed_brandt(db_session)
    # A pending and a declined request do not count.
    for status in (ConsentStatus.PENDING, ConsentStatus.DECLINED):
        db_session.add(Consent(application_id=app.id, type=ConsentType.HARD_PULL, status=status))
    await db_session.flush()
    fico_before = (await _field(db_session, app.id, "representative_fico")).value  # type: ignore[union-attr]
    events_before = await _count(
        db_session,
        select(func.count())
        .select_from(ActivityEvent)
        .where(ActivityEvent.application_id == app.id),
    )
    liabilities_before = await _count(
        db_session,
        select(func.count()).select_from(Liability).where(Liability.application_id == app.id),
    )
    calls_before = await _count(db_session, select(func.count()).select_from(IntegrationCall))

    with pytest.raises(HardPullConsentRequiredError) as excinfo:
        await perform_hard_pull(db_session, app.id)

    assert excinfo.value.status_code == 409
    assert (await _field(db_session, app.id, "representative_fico")).value == fico_before  # type: ignore[union-attr]
    assert await _field(db_session, app.id, "credit_pull_type") is None
    assert (
        await _count(
            db_session,
            select(func.count())
            .select_from(ActivityEvent)
            .where(ActivityEvent.application_id == app.id),
        )
        == events_before
    )
    assert (
        await _count(
            db_session,
            select(func.count()).select_from(Liability).where(Liability.application_id == app.id),
        )
        == liabilities_before
    )
    assert await _count(db_session, select(func.count()).select_from(IntegrationCall)) == (
        calls_before
    )


async def test_hard_pull_writes_middle_score(db_session: AsyncSession) -> None:
    """AC1 (service half): middle of three -> `representative_fico` with the
    CQ-028a contract (`source_ref="hard_pull"`), `credit_pull_type`,
    tradelines matched onto the imported liability, one event."""
    app = await _seed_brandt(db_session)
    await _accept(db_session, app.id)
    liabilities_before = await _count(
        db_session,
        select(func.count()).select_from(Liability).where(Liability.application_id == app.id),
    )

    result = await perform_hard_pull(db_session, app.id)

    assert result.fico == 690  # Experian 692, Equifax 688, TransUnion 690
    assert result.previous_fico == 692
    fico = await _field(db_session, app.id, "representative_fico")
    assert fico is not None and fico.value == 690 and fico.source_ref == "hard_pull"
    pull_type = await _field(db_session, app.id, "credit_pull_type")
    assert pull_type is not None and pull_type.value == "Hard_Pull"
    assert (
        await _count(
            db_session,
            select(func.count()).select_from(Liability).where(Liability.application_id == app.id),
        )
        == liabilities_before
    )
    completed = (
        (
            await db_session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.application_id == app.id,
                    ActivityEvent.type == "credit.hard_pull_completed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(completed) == 1
    payload: Any = completed[0].payload
    assert payload["fico"] == 690


async def test_fico_bucket_change_marks_stale(db_session: AsyncSession) -> None:
    """AC4: 692 -> 690 stays in 680-699 (quotes stay fresh); 692 -> 675
    crosses into 660-679 (quotes go stale)."""
    app = await _seed_brandt(db_session)
    assert app.los_loan_guid is not None
    stale_before = await _quotes_stale(db_session, app.id)
    assert stale_before and not any(stale_before)
    await _accept(db_session, app.id)

    same_bucket = await perform_hard_pull(db_session, app.id)

    assert same_bucket.bracket == same_bucket.previous_bracket == "680–699"
    assert same_bucket.quotes_marked_stale == 0
    assert not any(await _quotes_stale(db_session, app.id))

    await db_session.execute(
        update(ProviderCreditReport)
        .where(
            ProviderCreditReport.loan_number == app.los_loan_guid,
            ProviderCreditReport.pull_type == CreditPullType.HARD_PULL,
        )
        .values(experian_score=675, equifax_score=670, transunion_score=680, middle_score=675)
    )

    crossed = await perform_hard_pull(db_session, app.id)

    assert crossed.previous_bracket == "680–699" and crossed.bracket == "660–679"
    assert crossed.quotes_marked_stale == len(stale_before)
    assert all(await _quotes_stale(db_session, app.id))


async def test_tradelines_keep_manual_rows_and_add_new(db_session: AsyncSession) -> None:
    """Plan.md decision 4: LO-added rows untouched; a new tradeline is added;
    a matching imported row takes the bureau's amounts."""
    from app.features.applications.sections import provenance

    app = await _seed_brandt(db_session)
    manual = Liability(
        application_id=app.id,
        creditor_name="Chase",
        account_type="Credit Card",
        monthly_payment=50,
        balance=900,
    )
    db_session.add(manual)
    await db_session.flush()
    await provenance.mark_manual_row(db_session, app.id, "liabilities", manual.id)
    await db_session.execute(
        update(ProviderCreditReport)
        .where(
            ProviderCreditReport.loan_number == app.los_loan_guid,
            ProviderCreditReport.pull_type == CreditPullType.HARD_PULL,
        )
        .values(
            tradelines=[
                {"creditor": "Wells Fargo", "type": "Auto Loan", "monthly_payment": "425.00"},
                {"creditor": "Chase", "type": "Credit Card", "monthly_payment": "999.00"},
                {"creditor": "Discover", "type": "Credit Card", "monthly_payment": "35.00"},
            ]
        )
    )
    await _accept(db_session, app.id)

    result = await perform_hard_pull(db_session, app.id)

    assert (result.liabilities_updated, result.liabilities_added) == (1, 1)
    rows = {
        row.creditor_name: row
        for row in (
            await db_session.execute(
                select(Liability)
                .where(Liability.application_id == app.id)
                .execution_options(populate_existing=True)
            )
        ).scalars()
    }
    assert str(rows["Wells Fargo"].monthly_payment) == "425.00"
    assert str(rows["Chase"].monthly_payment) == "50.00"
    assert str(rows["Discover"].monthly_payment) == "35.00"
