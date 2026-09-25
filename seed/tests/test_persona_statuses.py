"""AC2/AC7.

This test file is written to be correct in both phases without editing, per
the orchestrator's plan: it reads `seed/pricing_seam.PRICING_AVAILABLE` to
know whether CQ-013 has merged yet.

- **Phase A** (CQ-013 not merged, `PRICING_AVAILABLE=False`): personas whose
  table status is `priced` stop at `ready_to_price` (verification passed,
  pricing stage skipped by the seam); Ben Ford still reaches
  `needs_attention` because his housing-history flag is CQ-012's rule alone;
  Aisha Coleman also stops at `ready_to_price` because her defect only
  surfaces via CQ-013's OB-required-field validation (spec.md, CQ-012's
  `write_flag` docstring). `test_grace_and_luis_downstream_rows` is skipped
  in this phase -- there is no priced quote yet for the D2 fixture layer to
  reference.
- **Phase B** (CQ-013 merged, `PRICING_AVAILABLE=True`): every persona's
  `seed_end_status` (the YAML fixture's own column, matching spec.md's table
  verbatim) is asserted directly, and the downstream-rows test runs for
  real.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.enums import ApplicationStatus
from app.features.applications.timeline.models import ActivityEvent
from app.features.notifications.outbox.models import OutboxEmail
from app.features.quotes.send.models import QuotePackage
from seed.pricing_seam import PRICING_AVAILABLE
from seed.tests.conftest import SeededBase


def _phase_a_expected_status(persona_key: str) -> ApplicationStatus:
    if persona_key == "ben_ford":
        # housing_history_24mo is a CQ-012 rule -- already merged, runs at
        # the Verify stage, no pricing needed.
        return ApplicationStatus.NEEDS_ATTENTION
    # Everyone else -- including aisha_coleman, whose "missing Occupancy"
    # flag only fires from CQ-013's OB-required-field validation -- clears
    # verification and waits at ready_to_price for the pricing seam.
    return ApplicationStatus.READY_TO_PRICE


async def test_persona_final_statuses_match_table(seeded_base: SeededBase) -> None:
    by_key = {p["key"]: p for p in seeded_base.personas}
    assert len(seeded_base.persona_results) == 10

    for result in seeded_base.persona_results:
        persona = by_key[result.key]
        if PRICING_AVAILABLE:
            expected = ApplicationStatus(persona["seed_end_status"])
        else:
            expected = _phase_a_expected_status(result.key)
        assert result.final_status == expected, (
            f"{result.key}: expected {expected.value}, got {result.final_status.value} "
            f"(PRICING_AVAILABLE={PRICING_AVAILABLE})"
        )


async def test_grace_and_luis_downstream_rows(seeded_base: SeededBase) -> None:
    if not PRICING_AVAILABLE:
        pytest.skip(
            "CQ-013 not merged yet (seed/pricing_seam.PRICING_AVAILABLE is False) -- "
            "no priced quote exists yet for Decision D2's fixture layer to reference."
        )

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
