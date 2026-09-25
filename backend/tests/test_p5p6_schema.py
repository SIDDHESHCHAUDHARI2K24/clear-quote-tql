"""P5/P6 foundation (docs/backlog/phase-p5-p6-foundation.md, E1/E8): the
shared migration's columns, defaults, partial unique index and backfills,
plus the new settings' defaults."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.enums import (
    ApplicationSource,
    ApplicationStatus,
    ApplicationTab,
    FlagSeverity,
    UserRole,
)
from app.features.applications.models import Application
from app.features.applications.verification.models import Flag
from app.features.applications.verification.rules import flag_message
from app.features.auth.models import BorrowerAccount, User
from app.features.borrower.consent.models import Consent, ConsentStatus, ConsentType
from app.features.clients.models import Client
from app.features.portal.apply.models import ApplicationDraft
from app.features.portal.support.models import SupportRequest

_MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "3b55187d53d7_p5p6_foundation.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("p5p6_foundation_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _make_borrower(db: AsyncSession) -> tuple[User, Client, BorrowerAccount]:
    lo = User(
        email=f"lo-{uuid.uuid4()}@clearquote.test",
        password_hash="x",
        role=UserRole.LO,
        full_name="Schema LO",
    )
    db.add(lo)
    await db.flush()
    client = Client(
        full_name="Schema Client", email=f"c-{uuid.uuid4()}@x.test", assigned_lo_id=lo.id
    )
    db.add(client)
    await db.flush()
    account = BorrowerAccount(client_id=client.id, email=f"b-{uuid.uuid4()}@x.test")
    db.add(account)
    await db.flush()
    return lo, client, account


async def _make_application(db: AsyncSession, lo: User, client: Client) -> Application:
    application = Application(client_id=client.id, lo_id=lo.id, status=ApplicationStatus.INTAKE)
    db.add(application)
    await db.flush()
    return application


async def test_new_tables_and_columns_exist(test_engine: AsyncEngine) -> None:
    def _inspect(sync_conn: sa.Connection) -> dict[str, set[str]]:
        inspector = sa.inspect(sync_conn)
        return {
            table: {c["name"] for c in inspector.get_columns(table)}
            for table in (
                "support_requests",
                "application_drafts",
                "consents",
                "flags",
                "applications",
            )
        }

    async with test_engine.connect() as conn:
        columns = await conn.run_sync(_inspect)

    assert {
        "reference",
        "borrower_account_id",
        "application_id",
        "topic",
        "message",
        "preferred_contact",
        "phone",
        "created_at",
    } <= columns["support_requests"]
    assert {
        "borrower_account_id",
        "data",
        "current_tab",
        "submitted_application_id",
        "created_at",
        "updated_at",
    } <= columns["application_drafts"]
    assert {
        "status",
        "requested_by",
        "requested_at",
        "decided_at",
        "expires_at",
        "typed_name",
        "user_agent",
        "text_version",
        "decline_reason",
    } <= columns["consents"]
    assert "message" in columns["flags"]
    assert "source" in columns["applications"]


async def test_application_source_defaults_to_los(db_session: AsyncSession) -> None:
    lo, client, _ = await _make_borrower(db_session)
    application = await _make_application(db_session, lo, client)
    await db_session.refresh(application)
    assert application.source is ApplicationSource.LOS

    raw: str = (
        await db_session.execute(
            sa.text(
                "INSERT INTO applications (id, client_id, lo_id, status, purpose) "
                "VALUES (:id, :client, :lo, 'intake', 'purchase') RETURNING source"
            ),
            {"id": uuid.uuid4(), "client": client.id, "lo": lo.id},
        )
    ).scalar_one()
    assert raw == "los"


async def test_pending_consent_needs_no_decision_fields(db_session: AsyncSession) -> None:
    lo, client, _ = await _make_borrower(db_session)
    application = await _make_application(db_session, lo, client)
    consent = Consent(application_id=application.id, type=ConsentType.HARD_PULL, requested_by=lo.id)
    db_session.add(consent)
    await db_session.flush()
    await db_session.refresh(consent)
    assert consent.status is ConsentStatus.PENDING
    assert consent.text_hash is None and consent.ip is None and consent.at is None


async def test_consent_status_server_default_is_accepted(db_session: AsyncSession) -> None:
    """Existing rows (written before the migration, with no status) become
    `accepted` -- the column's server default."""
    lo, client, _ = await _make_borrower(db_session)
    application = await _make_application(db_session, lo, client)
    status: str = (
        await db_session.execute(
            sa.text(
                "INSERT INTO consents (id, application_id, type, text_hash, ip, at) "
                "VALUES (:id, :app, 'hard_pull', 'h', '1.2.3.4', now()) RETURNING status"
            ),
            {"id": uuid.uuid4(), "app": application.id},
        )
    ).scalar_one()
    assert status == "accepted"


async def test_one_open_draft_per_borrower(db_session: AsyncSession) -> None:
    lo, client, account = await _make_borrower(db_session)
    application = await _make_application(db_session, lo, client)

    submitted = ApplicationDraft(
        borrower_account_id=account.id, submitted_application_id=application.id
    )
    first_open = ApplicationDraft(borrower_account_id=account.id)
    db_session.add_all([submitted, first_open])
    await db_session.flush()
    await db_session.refresh(first_open)
    assert first_open.data == {}
    assert first_open.current_tab == "you"

    async with db_session.begin_nested():
        db_session.add(ApplicationDraft(borrower_account_id=account.id))
        with pytest.raises(IntegrityError):
            await db_session.flush()


async def test_support_request_reference_is_unique(db_session: AsyncSession) -> None:
    _, _, account = await _make_borrower(db_session)
    db_session.add(
        SupportRequest(
            reference="SUP-AAAAA",
            borrower_account_id=account.id,
            topic="quote",
            message="A question about my quote.",
            preferred_contact="email",
        )
    )
    await db_session.flush()
    async with db_session.begin_nested():
        db_session.add(
            SupportRequest(
                reference="SUP-AAAAA",
                borrower_account_id=account.id,
                topic="other",
                message="Another question here.",
                preferred_contact="email",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


_BACKFILL_CASES = [
    ("occupancy_type", "ob_required_field", ApplicationTab.PRICING),
    ("RepresentativeFICO", "ob_required_field", ApplicationTab.PRICING),
    ("PurchasePrice", "ob_required_field", ApplicationTab.PRICING),
    ("LTV", "ob_required_field", ApplicationTab.PRICING),
    ("loan_amount", "ob_required_field", ApplicationTab.PRICING),
    ("current_residence_years", "housing_history_24mo", ApplicationTab.HOUSING),
    ("borrower_ssn", "ssn_format", ApplicationTab.BORROWERS),
    ("co_borrower_dob", "dob_format", ApplicationTab.BORROWERS),
    ("total_verified_assets", "assets_vs_ctc_reserves", ApplicationTab.ASSETS),
    ("dti_ratio", "dti_primary", ApplicationTab.PRICING),
    ("dscr_ratio", "dscr_bucket_unstable", ApplicationTab.PRICING),
    ("some_field", "unknown_rule", ApplicationTab.BORROWERS),
    ("PurchasePrice", "unknown_rule_2", ApplicationTab.BORROWERS),
]


async def test_flag_message_backfill_matches_flag_message(db_session: AsyncSession) -> None:
    """The migration's frozen SQL backfill writes exactly what
    `rules.flag_message` (used by `write_flag` for new rows) would."""
    lo, client, _ = await _make_borrower(db_session)
    application = await _make_application(db_session, lo, client)
    for field_key, rule, tab in _BACKFILL_CASES:
        db_session.add(
            Flag(
                application_id=application.id,
                tab=tab,
                field_key=field_key,
                rule=rule,
                severity=FlagSeverity.BLOCKING,
            )
        )
    await db_session.flush()

    await db_session.execute(sa.text(_load_migration()._FLAG_MESSAGE_BACKFILL))

    rows = (
        await db_session.execute(
            sa.select(Flag.rule, Flag.field_key, Flag.message).where(
                Flag.application_id == application.id
            )
        )
    ).all()
    assert len(rows) == len(_BACKFILL_CASES)
    for rule, field_key, message in rows:
        assert message == flag_message(rule, field_key), (rule, field_key)
    backfilled = {(rule, key): message for rule, key, message in rows}
    assert backfilled[("ob_required_field", "occupancy_type")] == (
        "Cannot price: missing Occupancy"
    )
    assert backfilled[("ob_required_field", "loan_amount")] == "Cannot price: missing Loan amount"


def test_p5p6_settings_defaults() -> None:
    fields = Settings.model_fields
    assert fields["support_inbox"].default == "support@tql.local"
    assert fields["stale_check_interval_seconds"].default == 3600
    assert fields["clock_now"].default is None
