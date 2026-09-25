"""`GET /applications/{id}/pricing`: the pricing panel's top section
(CQ-017 spec.md).

Returns the current scenario's inputs, every pricing-overridable enriched
field with its source badge and override state, and the `quote_engine`
breakdown for those inputs -- so the frontend never computes a single money
number itself (AGENTS.md: money math lives only in `quote_engine`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.core.errors import NotFoundError
from app.features.applications.models import Application
from app.features.applications.property.models import Property
from app.features.applications.verification.models import FieldValue
from app.features.pricing.engine.quote_engine import (
    LtvOutOfRangeError,
    compute_quote,
    insurance_annual_rate_from_amount,
)
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from app.features.pricing.enrichment.service import OVERRIDABLE_FIELD_KEYS, peek_source_value
from app.features.pricing.panel.schemas import (
    PricingFieldView,
    PricingInputsView,
    PricingViewResponse,
)
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.ob_request import (
    DEFAULT_DOWN_PAYMENT_INVESTMENT,
    DEFAULT_DOWN_PAYMENT_PRIMARY,
)
from app.features.quotes.builder.models import Quote

# The down-payment defaults for the one case this view has no persisted
# `Scenario` to read yet (a brand-new application that hasn't been
# auto-priced) come from `ob_request`, the single definition (P56-merge).


async def _get_application(db: AsyncSession, application_id: uuid.UUID) -> Application:
    application = await db.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    return application


async def _get_property(db: AsyncSession, application_id: uuid.UUID) -> Property | None:
    return (
        await db.execute(select(Property).where(Property.application_id == application_id))
    ).scalar_one_or_none()


async def _current_scenario(db: AsyncSession, application: Application) -> Scenario | None:
    """Same convention CQ-016's workspace summary uses for its header
    numbers (duplicated here rather than importing across a feature
    boundary owned by another item -- plan.md Decision 4): the scenario
    behind `recommended_quote_id`'s quote when set, else the most
    recently created `Scenario`, else `None`.
    """
    if application.recommended_quote_id is not None:
        quote = await db.get(Quote, application.recommended_quote_id)
        if quote is not None:
            scenario = await db.get(Scenario, quote.scenario_id)
            if scenario is not None:
                return scenario
    stmt = (
        select(Scenario)
        .where(Scenario.application_id == application.id)
        .order_by(Scenario.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def _current_quote(
    db: AsyncSession, application: Application, scenario: Scenario
) -> Quote | None:
    """plan.md Decision 5: prefer `recommended_quote_id`'s own quote (once
    CQ-018 sets one); else the current scenario's `"Par"`-labelled quote;
    else its earliest-priced quote. Without *some* rate, `compute_quote`
    can't run and the whole breakdown would be blank for every seeded demo
    persona today (no recommendation exists yet)."""
    if application.recommended_quote_id is not None:
        quote = await db.get(Quote, application.recommended_quote_id)
        if quote is not None and quote.scenario_id == scenario.id:
            return quote

    rows = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.scenario_id == scenario.id)
                .order_by(Quote.priced_at.asc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    for row in rows:
        if row.label == "Par":
            return row
    return rows[0]


def _default_strategy_and_ppp(application: Application) -> tuple[StrategyType, int | None]:
    if application.occupancy is Occupancy.PRIMARY:
        return StrategyType.PRIMARY, None
    if application.strategy is Strategy.LTR:
        return StrategyType.LTR, 5
    return StrategyType.STR, 5


_FICO_FIELD_KEY = "representative_fico"
_TAX_FIELD_KEY = "property_tax_annual_rate"
_INSURANCE_FIELD_KEY = "homeowners_ins_annual"
_HOA_FIELD_KEY = "hoa_fee_monthly"
_MARKET_RENT_FIELD_KEY = "market_rent_ltr"
_STR_REVENUE_FIELD_KEY = "gross_annual_revenue_str"


async def _field_decimals(
    db: AsyncSession, application_id: uuid.UUID, field_keys: Sequence[str]
) -> dict[str, Decimal]:
    """One batched `field_key IN (...)` query instead of one round trip per
    field (review finding) -- same batching `_field_views` already does."""
    rows = (
        (
            await db.execute(
                select(FieldValue).where(
                    FieldValue.application_id == application_id,
                    FieldValue.field_key.in_(field_keys),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.field_key: Decimal(str(row.value)) for row in rows if row.value is not None}


async def _inputs_and_config(
    db: AsyncSession, application: Application, scenario: Scenario | None
) -> tuple[ScenarioInputs | None, ConfigSnapshot, int | None]:
    """Returns `(inputs, config, prepayment_penalty_years)`. `inputs` is
    `None` when the application can't yet supply the raw pieces
    `ScenarioInputs` requires (no purchase price, a non-positive purchase
    price, or enrichment hasn't run) -- the response degrades to a `None`
    breakdown rather than 500ing.

    Purchase price / down payment % / strategy / PPP come from the current
    scenario when one exists (the LO's own chosen inputs), else the
    system-design defaults. The enriched fields (FICO, tax, insurance, HOA,
    rent/STR revenue) are **always** read fresh from `field_values`, never
    from a scenario's frozen `inputs` snapshot -- spec.md AC3 requires an
    override/revert to recompute the breakdown immediately, and a scenario
    snapshot only changes when CQ-018 reprices, not on every override.
    """
    if scenario is not None and isinstance(scenario.inputs, dict):
        try:
            scenario_inputs = ScenarioInputs.model_validate(scenario.inputs)
        except ValidationError:
            return None, ConfigSnapshot(), None
        purchase_price = scenario_inputs.purchase_price
        down_payment_pct = scenario_inputs.down_payment_pct
        strategy = scenario_inputs.strategy
        config = ConfigSnapshot()
        if isinstance(scenario.config_snapshot, dict):
            try:
                config = ConfigSnapshot.model_validate(scenario.config_snapshot)
            except ValidationError:
                config = ConfigSnapshot()
        ppp_years = scenario.inputs.get("prepayment_penalty_years")
    else:
        if application.requested_price is None:
            return None, ConfigSnapshot(), None
        strategy, ppp_years = _default_strategy_and_ppp(application)
        purchase_price = application.requested_price
        down_payment_pct = (
            DEFAULT_DOWN_PAYMENT_PRIMARY
            if strategy is StrategyType.PRIMARY
            else DEFAULT_DOWN_PAYMENT_INVESTMENT
        )
        config = ConfigSnapshot()

    # A non-positive purchase price would make `insurance_annual_rate_from_
    # amount` raise `NonPositivePriceError` below -- degrade to no
    # breakdown here instead (this file's own established pattern for
    # "can't price yet"), rather than letting that propagate as a 500.
    if purchase_price <= 0:
        return None, config, ppp_years

    strategy_field_key = (
        _MARKET_RENT_FIELD_KEY
        if strategy is StrategyType.LTR
        else _STR_REVENUE_FIELD_KEY
        if strategy is StrategyType.STR
        else None
    )
    field_keys = [_FICO_FIELD_KEY, _TAX_FIELD_KEY, _INSURANCE_FIELD_KEY, _HOA_FIELD_KEY]
    if strategy_field_key is not None:
        field_keys.append(strategy_field_key)
    fields = await _field_decimals(db, application.id, field_keys)

    fico = fields.get(_FICO_FIELD_KEY)
    tax_rate = fields.get(_TAX_FIELD_KEY)
    insurance_annual = fields.get(_INSURANCE_FIELD_KEY)
    hoa_monthly = fields.get(_HOA_FIELD_KEY) or Decimal("0")
    if fico is None or tax_rate is None or insurance_annual is None:
        return None, config, ppp_years

    market_rent_ltr = None
    str_gross_annual_revenue = None
    if strategy is StrategyType.LTR:
        market_rent_ltr = fields.get(_MARKET_RENT_FIELD_KEY)
        if market_rent_ltr is None:
            return None, config, ppp_years
    elif strategy is StrategyType.STR:
        str_gross_annual_revenue = fields.get(_STR_REVENUE_FIELD_KEY)
        if str_gross_annual_revenue is None:
            return None, config, ppp_years

    inputs = ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0"),
        strategy=strategy,
        fico=int(fico),
        property_tax_annual_rate=tax_rate,
        insurance_annual_rate=insurance_annual_rate_from_amount(purchase_price, insurance_annual),
        hoa_monthly=hoa_monthly,
        market_rent_ltr=market_rent_ltr,
        str_gross_annual_revenue=str_gross_annual_revenue,
    )
    return inputs, config, ppp_years


async def _field_views(
    db: AsyncSession, application: Application, property_: Property | None
) -> list[PricingFieldView]:
    rows = (
        (
            await db.execute(
                select(FieldValue).where(
                    FieldValue.application_id == application.id,
                    FieldValue.field_key.in_(OVERRIDABLE_FIELD_KEYS),
                )
            )
        )
        .scalars()
        .all()
    )
    views: list[PricingFieldView] = []
    for row in rows:
        overridden = row.overridden_by is not None
        original_value: Decimal | str | None = None
        if overridden and property_ is not None:
            original_value = await peek_source_value(db, application, property_, row.field_key)
        views.append(
            PricingFieldView(
                field_key=row.field_key,
                value=row.value,  # type: ignore[arg-type]
                source=row.source,
                source_ref=row.source_ref,
                overridden=overridden,
                original_value=original_value,
            )
        )
    return views


async def _has_stale_quotes(db: AsyncSession, application_id: uuid.UUID) -> bool:
    stmt = (
        select(Quote.id)
        .join(Scenario, Scenario.id == Quote.scenario_id)
        .where(Scenario.application_id == application_id, Quote.stale.is_(True))
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def get_pricing_view(db: AsyncSession, application: Application) -> PricingViewResponse:
    scenario = await _current_scenario(db, application)
    property_ = await _get_property(db, application.id)
    inputs, config, ppp_years = await _inputs_and_config(db, application, scenario)

    note_rate: Decimal | None = None
    if scenario is not None:
        quote = await _current_quote(db, application, scenario)
        if quote is not None:
            # `Quote.rate` is percent-scale (e.g. `7.500`); `ScenarioInputs.
            # note_rate` is a 0-1 fraction -- same conversion `dscr_loop.
            # inputs_with_priced_product` already does at this same
            # service-layer boundary (a scale conversion, not money math).
            note_rate = quote.rate / Decimal("100")

    breakdown = None
    if inputs is not None and note_rate is not None:
        priced_inputs = inputs.model_copy(update={"note_rate": note_rate})
        try:
            breakdown = compute_quote(priced_inputs, config)
        except LtvOutOfRangeError:
            breakdown = None

    fields = await _field_views(db, application, property_)
    has_stale_quotes = await _has_stale_quotes(db, application.id)

    if inputs is not None:
        inputs_view = PricingInputsView(
            purchase_price=inputs.purchase_price,
            down_payment_pct=inputs.down_payment_pct,
            strategy=inputs.strategy,
            prepayment_penalty_years=ppp_years,
            fico=inputs.fico,
            insurance_annual_rate=inputs.insurance_annual_rate,
        )
    else:
        strategy, default_ppp = _default_strategy_and_ppp(application)
        fico_raw = (await _field_decimals(db, application.id, [_FICO_FIELD_KEY])).get(
            _FICO_FIELD_KEY
        )
        inputs_view = PricingInputsView(
            purchase_price=application.requested_price or Decimal("0"),
            down_payment_pct=(
                DEFAULT_DOWN_PAYMENT_PRIMARY
                if strategy is StrategyType.PRIMARY
                else DEFAULT_DOWN_PAYMENT_INVESTMENT
            ),
            strategy=strategy,
            prepayment_penalty_years=ppp_years if ppp_years is not None else default_ppp,
            fico=int(fico_raw) if fico_raw is not None else None,
            insurance_annual_rate=None,
        )

    return PricingViewResponse(
        application_id=application.id,
        inputs=inputs_view,
        fields=fields,
        note_rate=note_rate,
        breakdown=breakdown,
        has_stale_quotes=has_stale_quotes,
    )
