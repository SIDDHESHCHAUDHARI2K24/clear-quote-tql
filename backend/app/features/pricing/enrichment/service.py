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

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FieldSource, FlagSeverity, Occupancy, Strategy
from app.core.errors import IntegrationError, NotFoundError, ValidationAppError
from app.features.applications.models import Application
from app.features.applications.property.models import Property
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.verification.models import FieldValue
from app.features.applications.verification.service import resolve_flag, write_flag
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.ob_request import build_ob_search_request
from app.features.quotes.builder.models import Quote
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

# CQ-010 review round 1, finding #1: every other missing OB field uses its
# own wire name as `flags.field_key` (e.g. `RepresentativeFICO`) -- but
# CQ-012's spec.md/tests (`applications/verification/tests/test_personas.py
# ::test_persona_7_write_flag`) pin persona 7 (Aisha Coleman)'s flag to
# `field_key="occupancy_type"` (the LOS/1003 field name, not the OB request
# name), matching system-design.md's "Cannot price: missing Occupancy"
# narrative at the field the LO would actually go fix on the Borrowers/
# Property tab. This is the one exception; every other missing field keeps
# its OB name unchanged (CQ-013's own `test_ob_validation.py` pins
# `RepresentativeFICO` verbatim).
_FIELD_KEY_OVERRIDES: dict[str, str] = {"Occupancy": "occupancy_type"}


def _flag_field_key(ob_field_name: str) -> str:
    return _FIELD_KEY_OVERRIDES.get(ob_field_name, ob_field_name)


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


_FieldFetchResult = tuple[Decimal | str, FieldSource, str | None]


async def _fetch_tax(
    db: AsyncSession, application: Application, property_: Property
) -> _FieldFetchResult:
    state, county = _property_state_and_county(property_)
    tax = await MockTaxClient(db).get_tax_rate(state, county or "")
    # `TaxRateDTO.annual_rate_pct` is a percent-scale number (e.g. `0.601`
    # for 0.601%), matching `provider_tax_rates`; `ScenarioInputs.
    # property_tax_annual_rate` is a 0-1 fraction like every other engine
    # `*_pct` field, so it's divided by 100 here, once, at the enrichment
    # boundary.
    fraction = tax.annual_rate_pct / Decimal("100")
    return fraction, FieldSource.SMARTASSET, None


async def _fetch_insurance(
    db: AsyncSession, application: Application, property_: Property
) -> _FieldFetchResult:
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
    return insurance.annual_premium, FieldSource.STEADILY, None


async def _fetch_hoa(
    db: AsyncSession, application: Application, property_: Property
) -> _FieldFetchResult:
    # Decision 5 (plan.md): no adapter or seeded table models a real HOA fee
    # yet (catalog: "Redfin / Zillow / listing"). Always $0 / DEFAULT.
    return Decimal("0.00"), FieldSource.DEFAULT, None


async def _fetch_market_rent_ltr(
    db: AsyncSession, application: Application, property_: Property
) -> _FieldFetchResult:
    if property_.zip is None:
        raise ValidationAppError("Cannot enrich market rent: property has no zip code.")
    rent = await MockRentClient(db).get_market_rent(property_.zip, property_.number_of_units)
    return rent.market_rent, FieldSource.RENTCAST, None


async def _fetch_str_revenue(
    db: AsyncSession, application: Application, property_: Property
) -> _FieldFetchResult:
    if property_.zip is None:
        raise ValidationAppError("Cannot enrich STR revenue: property has no zip code.")
    revenue = await MockStrClient(db).get_str_revenue(property_.zip, property_.number_of_units)
    return revenue.annual_revenue, FieldSource.AIRDNA, None


_FieldFetcher = Callable[[AsyncSession, Application, Property], Awaitable[_FieldFetchResult]]

# `field_key` -> the pure fetch function (adapter call only, no DB write)
# that both `_FIELD_HANDLERS` (persist) and `peek_source_value` (read-only,
# `pricing.panel`'s `original_value`) build on. Also doubles as the pinned
# list of override-able field keys (spec.md).
_FIELD_FETCHERS: dict[str, _FieldFetcher] = {
    "property_tax_annual_rate": _fetch_tax,
    "homeowners_ins_annual": _fetch_insurance,
    "hoa_fee_monthly": _fetch_hoa,
    "market_rent_ltr": _fetch_market_rent_ltr,
    "gross_annual_revenue_str": _fetch_str_revenue,
}


def _make_handler(field_key: str, fetcher: _FieldFetcher) -> _FieldHandler:
    async def _handler(
        db: AsyncSession, application: Application, property_: Property
    ) -> FieldValue:
        value, source, source_ref = await fetcher(db, application, property_)
        return await _upsert_field_value(db, application.id, field_key, value, source, source_ref)

    return _handler


_FieldHandler = Callable[[AsyncSession, Application, Property], Awaitable[FieldValue]]

# `field_key` -> the handler `revert_field_value` re-runs to restore the
# source value (fetch, then persist via `_upsert_field_value`).
_FIELD_HANDLERS: dict[str, _FieldHandler] = {
    field_key: _make_handler(field_key, fetcher) for field_key, fetcher in _FIELD_FETCHERS.items()
}

OVERRIDABLE_FIELD_KEYS: tuple[str, ...] = tuple(_FIELD_FETCHERS)
"""Public alias of the fixed 5-key override-able field list, for
cross-module readers (`pricing.panel`) that need it without reaching into
this module's private tables."""


async def peek_source_value(
    db: AsyncSession, application: Application, property_: Property, field_key: str
) -> Decimal | str | None:
    """Read-only "what would the source say right now" for `field_key` --
    calls the same adapter its own enrichment handler would (via the
    shared `_FIELD_FETCHERS` fetch function), but never writes to the DB.
    `pricing.panel`'s `original_value` for a currently-overridden field;
    there is no stored pre-override snapshot (plan.md Decision 7). Returns
    `None` if `field_key` isn't overridable, or the fetch itself fails for
    a reason unrelated to the override (e.g. a missing zip, a forced
    adapter failure) -- the panel shows no "original value" rather than
    500ing the whole pricing view over a peek.
    """
    fetcher = _FIELD_FETCHERS.get(field_key)
    if fetcher is None:
        return None
    try:
        value, _source, _source_ref = await fetcher(db, application, property_)
    except (ValidationAppError, IntegrationError):
        return None
    return value


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

    await _run("property_tax_annual_rate", _FIELD_HANDLERS["property_tax_annual_rate"])
    await _run("homeowners_ins_annual", _FIELD_HANDLERS["homeowners_ins_annual"])
    await _run("hoa_fee_monthly", _FIELD_HANDLERS["hoa_fee_monthly"])

    if application.occupancy is Occupancy.INVESTMENT:
        if application.strategy is Strategy.LTR:
            await _run("market_rent_ltr", _FIELD_HANDLERS["market_rent_ltr"])
        elif application.strategy is Strategy.STR:
            await _run("gross_annual_revenue_str", _FIELD_HANDLERS["gross_annual_revenue_str"])

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
                _flag_field_key(missing_field),
                _OB_REQUIRED_FLAG_RULE,
                FlagSeverity.BLOCKING,
            )
        await db.commit()
        raise

    possible_fields = list(ALWAYS_REQUIRED)
    if application.occupancy is Occupancy.INVESTMENT:
        possible_fields += CONDITIONALLY_REQUIRED_INVESTMENT
    for field_name in possible_fields:
        await resolve_flag(db, application_id, _flag_field_key(field_name), _OB_REQUIRED_FLAG_RULE)
    await db.commit()
    return True


_PRICING_AFFECTING_FIELDS = frozenset(_FIELD_HANDLERS.keys())
"""Every overridable pricing field (spec.md's fixed 5-key list) feeds
`compute_quote` directly (tax/insurance/HOA/rent/STR-revenue), so every one
of them is pricing-affecting by definition -- there is no narrower
allow-list (plan.md Decision 8)."""


async def _mark_application_quotes_stale(
    db: AsyncSession,
    application_id: uuid.UUID,
    field_key: str,
    actor_id: uuid.UUID,
    action: str,
    old_value: dict | list | str | float | bool | None,
    new_value: dict | list | str | float | bool | None,
) -> None:
    """CQ-017 spec.md AC3: an override/revert on a pricing-affecting field
    marks every one of that application's quotes stale (across every
    scenario/strategy group -- tax/insurance/HOA are scenario-independent,
    so a narrower "just the current scenario" scope would under-mark) and
    always writes one activity event, so the audit trail shows every
    pricing-affecting change even when every quote was already stale
    (only `quote_ids` may then be empty -- review finding). CQ-018 clears
    `stale` on reprice.

    A single `UPDATE ... WHERE stale = false RETURNING id` (not a SELECT
    then a separate UPDATE) so two concurrent overrides can't both read the
    same non-stale rows and each write their own activity event for the
    same transition (review finding: the DB's own row-level locking
    serializes the two UPDATEs instead).
    """
    if field_key not in _PRICING_AFFECTING_FIELDS:
        return
    stale_subquery = (
        select(Quote.id)
        .join(Scenario, Scenario.id == Quote.scenario_id)
        .where(Scenario.application_id == application_id, Quote.stale.is_(False))
    )
    result = await db.execute(
        update(Quote).where(Quote.id.in_(stale_subquery)).values(stale=True).returning(Quote.id)
    )
    quote_ids = result.scalars().all()
    db.add(
        ActivityEvent(
            application_id=application_id,
            actor=str(actor_id),
            type="quotes.marked_stale",
            payload={
                "field_key": field_key,
                "action": action,
                "old_value": str(old_value) if old_value is not None else None,
                "new_value": str(new_value) if new_value is not None else None,
                "quote_ids": [str(q) for q in quote_ids],
            },
            at=datetime.now(UTC),
        )
    )


async def _commit_or_flush(db: AsyncSession, commit: bool) -> None:
    if commit:
        await db.commit()
    else:
        await db.flush()


async def override_field_value(
    db: AsyncSession,
    application_id: uuid.UUID,
    field_key: str,
    value: Decimal | str,
    lo_id: uuid.UUID,
    *,
    commit: bool = True,
) -> FieldValue:
    """Overrides `field_key` and marks the application's quotes stale.

    `commit=False` (the `/field-values` route, PR #34 review m2) flushes
    instead, so the caller writes its own activity event under the same
    lock and commits the override and the event together."""
    if field_key not in _FIELD_HANDLERS:
        raise ValidationAppError(f"Not an overridable pricing field: {field_key}")
    json_value = str(value) if isinstance(value, Decimal) else value
    existing = await _existing_field_value(db, application_id, field_key)
    now = datetime.now(UTC)
    if existing is not None:
        old_value = existing.value
        existing.value = json_value
        existing.source = FieldSource.LO_OVERRIDE
        existing.source_ref = None
        existing.overridden_by = lo_id
        existing.overridden_at = now
        await _mark_application_quotes_stale(
            db, application_id, field_key, lo_id, "override", old_value, json_value
        )
        await _commit_or_flush(db, commit)
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
    await _mark_application_quotes_stale(
        db, application_id, field_key, lo_id, "override", None, json_value
    )
    await _commit_or_flush(db, commit)
    return row


async def revert_field_value(
    db: AsyncSession,
    application_id: uuid.UUID,
    field_key: str,
    actor_id: uuid.UUID,
    *,
    commit: bool = True,
) -> FieldValue:
    """Clears the override and re-runs that field's own enrichment fetch to
    restore the source value (there is no separate "pre-override value"
    column on `field_values` -- see plan.md Decision under AC3).
    `commit=False`: see `override_field_value`."""
    handler = _FIELD_HANDLERS.get(field_key)
    if handler is None:
        raise ValidationAppError(f"Not an overridable pricing field: {field_key}")

    existing = await _existing_field_value(db, application_id, field_key)
    if existing is None:
        raise NotFoundError(f"No field_values row for {field_key} on application {application_id}")
    old_value = existing.value
    existing.overridden_by = None
    existing.overridden_at = None
    await db.flush()

    application = await _get_application(db, application_id)
    property_ = await _get_property(db, application_id)
    row = await handler(db, application, property_)
    await _mark_application_quotes_stale(
        db, application_id, field_key, actor_id, "revert", old_value, row.value
    )
    await _commit_or_flush(db, commit)
    return row
