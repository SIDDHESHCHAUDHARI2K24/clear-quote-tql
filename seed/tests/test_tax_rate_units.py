"""P34-fix: guards the units bug where `seed/providers/tax_rates.yaml`
stored `annual_rate_pct` as a fraction (e.g. `0.0089`) instead of a percent
(`0.89`). `ProviderTaxRate.annual_rate_pct` and `TaxRateDTO.annual_rate_pct`
are percent-scale (matching `seed/providers/insurance_factors.yaml`'s
`"0.50"` for 0.50%; catalog examples: Buncombe 0.601%, Hillsborough 1.15%);
`backend/app/features/pricing/enrichment/service.py::_enrich_tax` divides
by 100 once, at the enrichment boundary, to produce the 0-1 fraction
`property_tax_annual_rate`. A yaml row stored as a fraction instead of a
percent makes every seeded persona's property tax ~100x too small.
"""

from decimal import Decimal

from sqlalchemy import select

from app.features.applications.verification.models import FieldValue
from seed.loader import load_provider_fixture
from seed.tests.conftest import SeededBase

# Real US county property-tax rates run roughly 0.1%-4%/yr (catalog
# examples: Buncombe NC 0.601%, Hillsborough FL 1.15%).
_MIN_PERCENT = Decimal("0.1")
_MAX_PERCENT = Decimal("4.0")


def test_tax_rates_yaml_annual_rate_pct_is_percent_scale() -> None:
    """AC: every `tax_rates.yaml` row's `annual_rate_pct`, read as a percent
    (not a fraction), is a sane county property-tax rate."""
    rows = load_provider_fixture("tax_rates.yaml")
    assert rows, "tax_rates.yaml has no rows"
    for row in rows:
        rate = Decimal(str(row["annual_rate_pct"]))
        assert _MIN_PERCENT <= rate <= _MAX_PERCENT, (
            f"{row['county']}, {row['state']}: annual_rate_pct={rate} is not a sane "
            f"percent ({_MIN_PERCENT}-{_MAX_PERCENT}); it looks like a fraction "
            "was stored instead of a percent (see _enrich_tax's /100 conversion)."
        )


async def test_seeded_persona_property_tax_annual_rate_is_realistic_fraction(
    seeded_base: SeededBase,
) -> None:
    """AC: a seeded persona's `property_tax_annual_rate` field value, as the
    0-1 fraction the engine consumes, lands in a realistic range -- proof
    the enrichment boundary's /100 conversion is being applied to
    percent-scale data, not fraction-scale data already 100x too small."""
    db = seeded_base.db
    by_key = {r.key: r for r in seeded_base.persona_results}
    marcus = by_key["marcus_hale"]

    row = (
        await db.execute(
            select(FieldValue).where(
                FieldValue.application_id == marcus.application_id,
                FieldValue.field_key == "property_tax_annual_rate",
            )
        )
    ).scalar_one()

    fraction = Decimal(str(row.value))
    assert Decimal("0.001") <= fraction <= Decimal("0.04"), (
        f"marcus_hale property_tax_annual_rate={fraction} is not a realistic "
        "0-1 fraction (0.001-0.04) -- looks 100x too small."
    )
