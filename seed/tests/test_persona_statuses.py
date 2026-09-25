"""AC2/AC7 -- Phase B: CQ-013 is merged, `seed_persona` runs the real
pricing stage end to end, so every persona's `seed_end_status` (the YAML
fixture's own column, matching spec.md's persona table verbatim) is
asserted directly."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.enums import ApplicationStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.notifications.outbox.models import OutboxEmail
from app.features.quotes.send.models import QuotePackage, QuotePackageVersion
from seed.tests.conftest import SeededBase


async def test_persona_final_statuses_match_table(seeded_base: SeededBase) -> None:
    by_key = {p["key"]: p for p in seeded_base.personas}
    assert len(seeded_base.persona_results) == 10

    for result in seeded_base.persona_results:
        persona = by_key[result.key]
        expected = ApplicationStatus(persona["seed_end_status"])
        assert result.final_status == expected, (
            f"{result.key}: expected {expected.value}, got {result.final_status.value}"
        )


async def test_grace_and_luis_downstream_rows(seeded_base: SeededBase) -> None:
    db = seeded_base.db
    by_key = {r.key: r for r in seeded_base.persona_results}

    grace = by_key["grace_kim"]
    assert grace.final_status is ApplicationStatus.SENT
    grace_stmt = select(QuotePackage).where(QuotePackage.application_id == grace.application_id)
    grace_package = (await db.execute(grace_stmt)).scalar_one()
    assert grace_package.sent_at is not None
    days_ago = (datetime.now(UTC) - grace_package.sent_at).days
    assert 24 <= days_ago <= 26  # "sent 25 days ago" (spec.md persona table)
    assert grace_package.borrower_action is None

    luis = by_key["luis_romero"]
    assert luis.final_status is ApplicationStatus.OPTION_SELECTED
    luis_stmt = select(QuotePackage).where(QuotePackage.application_id == luis.application_id)
    luis_package = (await db.execute(luis_stmt)).scalar_one()
    assert luis_package.borrower_action is not None
    assert luis_package.viewed_at is not None

    luis_events = (
        (
            await db.execute(
                select(ActivityEvent).where(ActivityEvent.application_id == luis.application_id)
            )
        )
        .scalars()
        .all()
    )
    assert {e.type for e in luis_events} >= {"quote.sent", "quote.viewed", "quote.option_selected"}

    luis_emails = (
        (
            await db.execute(
                select(OutboxEmail).where(OutboxEmail.application_id == luis.application_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(luis_emails) >= 1


async def test_grace_and_luis_have_quote_package_versions(seeded_base: SeededBase) -> None:
    """CQ-022 spec.md "Seed": `apply_send_fixture` now also freezes a
    `quote_package_versions` row (D2) through the same factory CQ-020's
    send workflow will use, so `/report/{token}` works for these personas
    after `make demo-reset` -- Grace's version is past its 21-day expiry
    (H2), Luis's is viewed with a `borrower_action`."""
    db = seeded_base.db
    by_key = {r.key: r for r in seeded_base.persona_results}

    grace = by_key["grace_kim"]
    grace_package = (
        await db.execute(
            select(QuotePackage).where(QuotePackage.application_id == grace.application_id)
        )
    ).scalar_one()
    grace_version = (
        await db.execute(
            select(QuotePackageVersion).where(QuotePackageVersion.package_id == grace_package.id)
        )
    ).scalar_one()
    assert grace_version.version == 1
    assert grace_version.superseded is False
    assert grace_version.viewed_at is None
    assert grace_version.borrower_action is None
    assert datetime.now(UTC) > grace_version.expires_at  # sent 25 days ago > 21-day expiry (H2)
    assert isinstance(grace_version.snapshot, dict)
    assert grace_version.snapshot["header"]["expired"] is False  # frozen false; recomputed live

    luis = by_key["luis_romero"]
    luis_package = (
        await db.execute(
            select(QuotePackage).where(QuotePackage.application_id == luis.application_id)
        )
    ).scalar_one()
    luis_version = (
        await db.execute(
            select(QuotePackageVersion).where(QuotePackageVersion.package_id == luis_package.id)
        )
    ).scalar_one()
    assert luis_version.viewed_at is not None
    luis_borrower_action = luis_version.borrower_action
    assert isinstance(luis_borrower_action, dict)
    assert luis_borrower_action["type"] == "option_selected"
    assert datetime.now(UTC) <= luis_version.expires_at  # sent 3 days ago, well within 21 days
