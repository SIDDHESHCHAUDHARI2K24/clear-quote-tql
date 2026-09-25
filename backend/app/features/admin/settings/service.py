"""`GET /admin/settings` (spec.md "Settings", Admin, read-only).

Every value the spec lists (fee constants, insurance rate, STR expense
ratio, land/accelerated percentages, bonus depreciation, marginal tax
rate, reserves months, stale days) is already a 1:1 `settings` table row
(`seed_settings_defaults`; see `features/settings/tests/test_defaults.py`'s
`EXPECTED` dict) -- `source="settings_table"`. The two "default down
payment" values the spec also lists have no `settings` row: they're
hardcoded in `pricing/scenarios/service.py`
(`DEFAULT_DOWN_PAYMENT_PRIMARY`/`_INVESTMENT`, public aliases -- review
finding 6) -- imported directly below (source="code_default", plan.md
decision 7) rather than re-hardcoded here, per code review: two
independently-maintained copies of the same literal would let this page
silently show a stale default if the pricing module's own constant ever
changes.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.admin.settings.schemas import SettingValue
from app.features.pricing.scenarios.service import (
    DEFAULT_DOWN_PAYMENT_INVESTMENT,
    DEFAULT_DOWN_PAYMENT_PRIMARY,
)
from app.features.settings.models import Setting

_CODE_DEFAULTS: dict[str, tuple[float, str]] = {
    "default_down_payment_primary_pct": (
        float(DEFAULT_DOWN_PAYMENT_PRIMARY),
        "Default down payment used when creating a PRIMARY scenario with none given",
    ),
    "default_down_payment_investment_pct": (
        float(DEFAULT_DOWN_PAYMENT_INVESTMENT),
        "Default down payment used when creating an investment (LTR/STR) scenario with none given",
    ),
}


async def list_settings(db: AsyncSession) -> list[SettingValue]:
    rows = (await db.execute(select(Setting).order_by(Setting.key))).scalars().all()
    values = [
        SettingValue(
            key=row.key, value=row.value, description=row.description, source="settings_table"
        )
        for row in rows
    ]
    for key, (value, description) in _CODE_DEFAULTS.items():
        values.append(
            SettingValue(key=key, value=value, description=description, source="code_default")
        )
    return sorted(values, key=lambda v: v.key)
