"""AC6: `seed_settings_defaults` inserts every documented default key/value."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.settings.models import Setting

EXPECTED: dict[str, float] = {
    "fee_lender_processing": 995.00,
    "fee_lender_underwriting": 795.00,
    "title_pct": 0.007,
    "str_expense_ratio": 0.20,
    "insurance_default_pct": 0.005,
    "land_allocation_pct": 0.20,
    "accelerated_property_pct": 0.25,
    "bonus_depreciation_pct": 1.00,
    "investor_marginal_tax_rate": 0.32,
    "prepaid_interest_days": 15,
    "prepaid_insurance_months": 14,
    "prepaid_tax_months": 3,
    "reserves_months_primary": 2,
    "reserves_months_investment": 6,
    "stale_quote_days": 21,
    "report_link_expiry_days": 7,
}


async def test_every_documented_default_key_present_with_documented_value(
    db_session: AsyncSession,
) -> None:
    rows = (await db_session.execute(select(Setting))).scalars().all()
    by_key = {row.key: row.value for row in rows}

    missing = set(EXPECTED) - set(by_key)
    assert not missing, f"seed_settings_defaults did not insert: {missing}"

    for key, expected_value in EXPECTED.items():
        actual_value = by_key[key]
        assert isinstance(actual_value, int | float), f"{key}: not numeric: {actual_value!r}"
        assert actual_value == expected_value, (
            f"{key}: expected {expected_value}, got {actual_value}"
        )
