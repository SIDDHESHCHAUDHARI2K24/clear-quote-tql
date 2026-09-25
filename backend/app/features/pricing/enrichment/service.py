"""`enrich_pricing_fields`/`validate_ob_required_fields`: the two function
names CQ-011's Temporal pipeline (`enrich_application`/
`validate_pricing_inputs` activities) and CQ-010's `demo-reset` call by name
(see spec.md), plus the LO's manual override/revert actions on the same
`field_values` rows.

Enrichment writes one `field_values` row per pricing field, `source` set to
`FieldSource`'s enum *value* (not a display string — the LO Console's
`SourceBadge` maps that onto "SmartAsset"/"Steadily"/etc. itself). It is
idempotent: any `field_key` with `overridden_by is not null` is left alone.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FieldSource, FlagSeverity, Occupancy, Strategy
from app.core.errors import NotFoundError, ValidationAppError
from app.features.applications.models import Application
from app.features.applications.property.models import Property
from app.features.applications.verification.models import FieldValue
from app.features.applications.verification.service import resolve_flag, write_flag
from app.features.pricing.scenarios.ob_request import build_ob_search_request
from app.integrations.common.errors import PricingValidationError
from app.integrations.insurance.mock import MockInsuranceClient
from app.integrations.pricing.mock import (
    ALWAYS_REQUIRED,
    CONDITIONALLY_REQUIRED_INVESTMENT,
    MockPricingClient,
)
from app.integrations.rent.mock import MockRentClient
from app.integrations.str.mock import MockStrClient
from app.integrations.tax.mock import MockTaxClient

_OB_REQUIRED_FLAG_RULE = "ob_required_field"


@dataclass(frozen=True)
class EnrichmentResult:
    field_keys_written: list[str] = field(default_factory=list)
    """The `field_values.field_key`s this call actually wrote (a
    previously-overridden field is skipped and absent from this list)."""


async def _get_application(db: AsyncSession, application_id: uuid.UUID) -> Application:
    application = await db.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    return application


async def _get_property(db: AsyncSession, application_id: uuid.UUID) -> Property:
    property_ = (
        await db.execute(select(Property).where(Property.application_id == application_id))
    ).scalar_one_or_none()
    if property_ is None:
        raise NotFoundError(f"Property not found for application: {application_id}")
    return property_


async def _existing_field_value(
    db: AsyncSession, application_id: uuid.UUID, field_key: str
) -> FieldValue | None:
    return (
        await db.execute(
            select(FieldValue).where(
                FieldValue.application_id == application_id, FieldValue.field_key == field_key
            )
        )
    ).scalar_one_or_none()


async def _upsert_field_value(
    db: AsyncSession,
    application_id: uuid.UUID,
    field_key: str,
    value: Decimal | str,
    source: FieldSource,
    source_ref: str | None = None,
) -> FieldValue:
    existing = await _existing_field_value(db, application_id, field_key)
    json_value = str(value) if isinstance(value, Decimal) else value
    if existing is not None:
        existing.value = json_value
        existing.source = source
        existing.source_ref = source_ref
        await db.flush()
        return existing
    row = FieldValue(
        application_id=application_id,
        field_key=field_key,
        value=json_value,
        source=source,
        source_ref=source_ref,
    )
    db.add(row)
    await db.flush()
    return row


def _property_state_and_county(property_: Property) -> tuple[str, str | None]:
    state = property_.state or (property_.buy_box_states[0] if property_.buy_box_states else None)
    if state is None:
        raise ValidationAppError(
            "Cannot enrich pricing fields: no property state on file or in the buy box."
        )
    return state, property_.county


async def _enrich_tax(
    db: AsyncSession, application: Application, property_: Property
) -> FieldValue:
    state, county = _property_state_and_county(property_)
    tax = await MockTaxClient(db).get_tax_rate(state, county or "")
    # `TaxRateDTO.annual_rate_pct` is a percent-scale number (e.g. `0.601`
    # for 0.601%), matching `provider_tax_rates`; `ScenarioInputs.
    # property_tax_annual_rate` is a 0-1 fraction like every other engine
    # `*_pct` field, so it's divided by 100 here, once, at the enrichment
    # boundary.
    fraction = tax.annual_rate_pct / Decimal("100")
    return await _upsert_field_value(
        db, application.id, "property_tax_annual_rate", fraction, FieldSource.SMARTASSET
    )


async def _enrich_insurance(
    db: AsyncSession, application: Application, property_: Property
) -> FieldValue:
    if application.requested_price is None:
        raise ValidationAppError(
            "Cannot enrich pricing fields: application has no requested_price."
        )
    state, _county = _property_state_and_county(property_)
    insurance = await MockInsuranceClient(db).get_insurance_estimate(
        state, application.requested_price
    )
    # `homeowners_ins_annual` is the dollar premium itself (catalog: Currency),
    # unlike `property_tax_annual_rate` which is a rate.
    return await _upsert_field_value(
        db, application.id, "homeowners_ins_annual", insurance.annual_premium, FieldSource.STEADILY
    )


async def _enrich_hoa(
    db: AsyncSession, application: Application, property_: Property
) -> FieldValue:
    # Decision 5 (plan.md): no adapter or seeded table models a real HOA fee
    # yet (catalog: "Redfin / Zillow / listing"). Always $0 / DEFAULT.
    return await _upsert_field_value(
        db, application.id, "hoa_fee_monthly", Decimal("0.00"), FieldSource.DEFAULT
    )


async def _enrich_market_rent_ltr(
    db: AsyncSession, application: Application, property_: Property
) -> FieldValue:
    if property_.zip is None:
        raise ValidationAppError("Cannot enrich market rent: property has no zip code.")
    rent = await MockRentClient(db).get_market_rent(property_.zip, property_.number_of_units)
    return await _upsert_field_value(
        db, application.id, "market_rent_ltr", rent.market_rent, FieldSource.RENTCAST
    )


async def _enrich_str_revenue(
    db: AsyncSession, application: Application, property_: Property
) -> FieldValue:
    if property_.zip is None:
        raise ValidationAppError("Cannot enrich STR revenue: property has no zip code.")
    revenue = await MockStrClient(db).get_str_revenue(property_.zip, property_.number_of_units)
    return await _upsert_field_value(
        db, application.id, "gross_annual_revenue_str", revenue.annual_revenue, FieldSource.AIRDNA
    )


_FieldHandler = Callable[[AsyncSession, Application, Property], Awaitable[FieldValue]]

# `field_key` -> the handler `revert_field_value` re-runs to restore the
# source value. Also doubles as the pinned list of override-able field keys
# (spec.md).
_FIELD_HANDLERS: dict[str, _FieldHandler] = {
    "property_tax_annual_rate": _enrich_tax,
    "homeowners_ins_annual": _enrich_insurance,
    "hoa_fee_monthly": _enrich_hoa,
    "market_rent_ltr": _enrich_market_rent_ltr,
    "gross_annual_revenue_str": _enrich_str_revenue,
}


async def enrich_pricing_fields(db: AsyncSession, application_id: uuid.UUID) -> EnrichmentResult:
    """Writes tax/insurance/HOA/rent-or-STR `field_values`, skipping any
    field already overridden by the LO. Called by CQ-011's `enrich_
    application` activity and CQ-010's `demo-reset`, and by the pricing
    panel's manual "re-enrich" action.
    """
    application = await _get_application(db, application_id)
    property_ = await _get_property(db, application_id)

    written: list[str] = []

    async def _run(field_key: str, handler: _FieldHandler) -> None:
        existing = await _existing_field_value(db, application_id, field_key)
        if existing is not None and existing.overridden_by is not None:
            return
        await handler(db, application, property_)
        written.append(field_key)

    await _run("property_tax_annual_rate", _enrich_tax)
    await _run("homeowners_ins_annual", _enrich_insurance)
    await _run("hoa_fee_monthly", _enrich_hoa)

    if application.occupancy is Occupancy.INVESTMENT:
        if application.strategy is Strategy.LTR:
            await _run("market_rent_ltr", _enrich_market_rent_ltr)
        elif application.strategy is Strategy.STR:
            await _run("gross_annual_revenue_str", _enrich_str_revenue)

    await db.commit()
    return EnrichmentResult(field_keys_written=written)


async def validate_ob_required_fields(db: AsyncSession, application_id: uuid.UUID) -> bool:
    """Builds the OB request and calls `PricingClient.get_priced_products`
    once, purely to surface `PricingValidationError` (CQ-009) if any
    required field is missing -- called by CQ-011's `validate_pricing_
    inputs` activity and CQ-010's `demo-reset`.

    Writes a `blocking` flag per missing field (persona 7, Aisha Coleman's
    "Cannot price: missing Occupancy") and resolves any such flag once the
    fields are all present, so the Pricing tab's flag count tracks the
    field, not just the pipeline's transient exception.
    """
    application = await _get_application(db, application_id)
    request = await build_ob_search_request(db, application_id)

    try:
        await MockPricingClient(db).get_priced_products(request)
    except PricingValidationError as exc:
        for missing_field in exc.missing_fields:
            await write_flag(
                db,
                application_id,
                ApplicationTab.PRICING,
                missing_field,
                _OB_REQUIRED_FLAG_RULE,
                FlagSeverity.BLOCKING,
            )
        await db.commit()
        raise

    possible_fields = list(ALWAYS_REQUIRED)
    if application.occupancy is Occupancy.INVESTMENT:
        possible_fields += CONDITIONALLY_REQUIRED_INVESTMENT
    for field_name in possible_fields:
        await resolve_flag(db, application_id, field_name, _OB_REQUIRED_FLAG_RULE)
    await db.commit()
    return True


async def override_field_value(
    db: AsyncSession,
    application_id: uuid.UUID,
    field_key: str,
    value: Decimal | str,
    lo_id: uuid.UUID,
) -> FieldValue:
    if field_key not in _FIELD_HANDLERS:
        raise ValidationAppError(f"Not an overridable pricing field: {field_key}")
    json_value = str(value) if isinstance(value, Decimal) else value
    existing = await _existing_field_value(db, application_id, field_key)
    now = datetime.now(UTC)
    if existing is not None:
        existing.value = json_value
        existing.source = FieldSource.LO_OVERRIDE
        existing.source_ref = None
        existing.overridden_by = lo_id
        existing.overridden_at = now
        await db.commit()
        return existing
    row = FieldValue(
        application_id=application_id,
        field_key=field_key,
        value=json_value,
        source=FieldSource.LO_OVERRIDE,
        overridden_by=lo_id,
        overridden_at=now,
    )
    db.add(row)
    await db.commit()
    return row


async def revert_field_value(
    db: AsyncSession, application_id: uuid.UUID, field_key: str
) -> FieldValue:
    """Clears the override and re-runs that field's own enrichment fetch to
    restore the source value (there is no separate "pre-override value"
    column on `field_values` -- see plan.md Decision under AC3)."""
    handler = _FIELD_HANDLERS.get(field_key)
    if handler is None:
        raise ValidationAppError(f"Not an overridable pricing field: {field_key}")

    existing = await _existing_field_value(db, application_id, field_key)
    if existing is None:
        raise NotFoundError(f"No field_values row for {field_key} on application {application_id}")
    existing.overridden_by = None
    existing.overridden_at = None
    await db.flush()

    application = await _get_application(db, application_id)
    property_ = await _get_property(db, application_id)
    row = await handler(db, application, property_)
    await db.commit()
    return row
