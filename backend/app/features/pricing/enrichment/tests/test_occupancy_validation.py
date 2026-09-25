"""CQ-010 review round 1, finding #1: persona 7 (Aisha Coleman)'s exact
"Cannot price: missing Occupancy" message and `flags.field_key ==
"occupancy_type"` (CQ-012's spec.md/tests pin this field_key exactly --
`applications/verification/tests/test_personas.py::test_persona_7_write_flag`),
pinned directly against `validate_ob_required_fields` so a future
regression to some other field/wording is caught here, independent of the
full seed pipeline. Also covers the resolve direction: once
`applications.occupancy` is set, the flag clears.
"""

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.applications.verification.models import Flag
from app.features.pricing.enrichment.service import (
    _OB_REQUIRED_FLAG_RULE,
    validate_ob_required_fields,
)
from app.integrations.common.errors import PricingValidationError


async def _occupancy_flag(db_session: AsyncSession, application_id: object) -> Flag | None:
    return (
        await db_session.execute(
            select(Flag).where(
                Flag.application_id == application_id,
                Flag.field_key == "occupancy_type",
                Flag.rule == _OB_REQUIRED_FLAG_RULE,
            )
        )
    ).scalar_one_or_none()


async def test_missing_occupancy_raises_exact_message_and_flags_occupancy_type(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    """`applications.occupancy is None` (persona 7's exact state after
    `import_from_los` finds no `occupancy_type` on her LOS record) must
    surface as `Occupancy` -- and only `Occupancy` -- missing, matching
    system-design.md's wording verbatim."""
    application = await make_application(occupancy=None, strategy=Strategy.LTR)
    await set_field_value(application.id, "representative_fico", "740")

    with pytest.raises(PricingValidationError) as exc_info:
        await validate_ob_required_fields(db_session, application.id)

    assert exc_info.value.missing_fields == ["Occupancy"]
    assert exc_info.value.message == "Cannot price: missing Occupancy"

    flag = await _occupancy_flag(db_session, application.id)
    assert flag is not None
    assert flag.tab is ApplicationTab.PRICING
    assert flag.severity is FlagSeverity.BLOCKING
    assert flag.resolved_at is None


async def test_setting_occupancy_resolves_the_occupancy_type_flag(
    db_session: AsyncSession,
    make_application: Callable[..., Awaitable[Application]],
    set_field_value: Callable[..., Awaitable[object]],
) -> None:
    application = await make_application(occupancy=None, strategy=Strategy.LTR)
    await set_field_value(application.id, "representative_fico", "740")

    with pytest.raises(PricingValidationError):
        await validate_ob_required_fields(db_session, application.id)
    assert await _occupancy_flag(db_session, application.id) is not None

    # The LO (or a re-import) fills in occupancy -- the same fix path
    # persona 7's real "resume after fix" story depends on.
    application.occupancy = Occupancy.INVESTMENT
    await db_session.flush()
    await db_session.commit()

    result = await validate_ob_required_fields(db_session, application.id)

    assert result is True
    flag = await _occupancy_flag(db_session, application.id)
    assert flag is not None
    assert flag.resolved_at is not None
