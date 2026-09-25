"""AC2/AC7 -- Phase B: CQ-013 is merged, `seed_persona` runs the real
pricing stage end to end, so every persona's `seed_end_status` (the YAML
fixture's own column, matching spec.md's persona table verbatim) is
asserted directly."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.enums import ApplicationStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.notifications.outbox.models import OutboxEmail
from app.features.quotes.send.models import QuotePackage
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
