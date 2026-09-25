"""`create_scenario`, `create_default_scenarios`, `select_par_and_buydown`
and `auto_price` -- the Quote Builder's server side (spec.md).

`auto_price` is the exact function name CQ-011's `auto_price_application`
activity and CQ-010's `demo-reset` call.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Occupancy, Strategy
from app.core.errors import NotFoundError, ValidationAppError
from app.features.applications.models import Application
from app.features.applications.verification.models import FieldValue
from app.features.pricing.engine.quote_engine import (
    NonPositivePriceError,
    compute_quote,
    insurance_annual_rate_from_amount,
)
from app.features.pricing.engine.types import (
    ConfigSnapshot,
    DSCRBucket,
    QuoteComputation,
    ScenarioInputs,
    StrategyType,
)
from app.features.pricing.scenarios.dscr_loop import (
    ASSUMED_DSCR_BY_BUCKET,
    inputs_with_priced_product,
    run_two_pass_dscr,
)
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.ob_request import ObRequestOverrides, build_ob_search_request
from app.features.quotes.builder.models import Quote
from app.integrations.pricing.mock import MockPricingClient
from app.integrations.pricing.schemas import PricedProductDTO

_DEFAULT_DOWN_PAYMENT_PRIMARY = Decimal("0.20")
_DEFAULT_DOWN_PAYMENT_INVESTMENT = Decimal("0.25")
_MI_REMOVAL_DOWN_PAYMENT = Decimal("0.20")
_BUYDOWN_MAX_POINTS = Decimal("0.01")
"""1.00 point == 0.01 as a fraction, the same scale as `PricedProductDTO.
discount_points_pct` (see `MockPricingClient`'s own `_BUYDOWN_POINTS_HIGH`)."""


@dataclass(frozen=True)
class PricingResult:
    """CQ-011's `auto_price_application` activity output."""

    scenario_ids: list[uuid.UUID]
    quote_ids: list[uuid.UUID]


@dataclass(frozen=True)
class ScenarioGroupResult:
    scenario_id: uuid.UUID
    quote_ids: list[uuid.UUID]
    collapsed: bool
    note: str | None


@dataclass(frozen=True)
class DefaultScenarioSetResult:
    groups: list[ScenarioGroupResult]

    @property
    def scenario_ids(self) -> list[uuid.UUID]:
        return [group.scenario_id for group in self.groups]

    @property
    def quote_ids(self) -> list[uuid.UUID]:
        return [quote_id for group in self.groups for quote_id in group.quote_ids]

    def as_pricing_result(self) -> PricingResult:
        return PricingResult(scenario_ids=self.scenario_ids, quote_ids=self.quote_ids)


def select_par_and_buydown(
    rows: list[PricedProductDTO],
) -> tuple[PricedProductDTO, PricedProductDTO | None]:
    """Save & AutoQuote's selection (spec.md): best par = `is_par_rate` row,
    tie-broken by minimum `abs(discount_points_pct)`, then lowest
    `note_rate`, then `investor_name` (deterministic). Best buydown = lowest
    `note_rate` among rows with `0 < discount_points_pct <= 1.00 point`;
    `None` if no row qualifies.
    """
    par_candidates = [row for row in rows if row.is_par_rate]
    if not par_candidates:
        raise ValueError("select_par_and_buydown: no row has is_par_rate=True.")
    best_par = min(
        par_candidates,
        key=lambda row: (abs(row.discount_points_pct), row.note_rate, row.investor_name),
    )

    buydown_candidates = [
        row for row in rows if Decimal("0") < row.discount_points_pct <= _BUYDOWN_MAX_POINTS
    ]
    best_buydown = (
        min(buydown_candidates, key=lambda row: row.note_rate) if buydown_candidates else None
    )
    return best_par, best_buydown


async def _get_application(db: AsyncSession, application_id: uuid.UUID) -> Application:
    application = await db.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"Application not found: {application_id}")
    return application


def _purchase_price(application: Application) -> Decimal:
    # Decision 7 (plan.md): no purchasing-power engine exists anywhere in
    # the merged codebase; the "else max purchasing power" fallback from
    # system-design is out of scope.
    if application.requested_price is None:
        raise ValidationAppError("Cannot price: application has no requested_price.")
    return application.requested_price


def _strategy_type(application: Application) -> StrategyType:
    if application.occupancy is Occupancy.PRIMARY:
        return StrategyType.PRIMARY
    if application.strategy is Strategy.LTR:
        return StrategyType.LTR
    if application.strategy is Strategy.STR:
        return StrategyType.STR
    raise ValidationAppError("Cannot price: investment application has no strategy set.")


async def _field_decimal(
    db: AsyncSession, application_id: uuid.UUID, field_key: str
) -> Decimal | None:
    row = (
        await db.execute(
            select(FieldValue).where(
                FieldValue.application_id == application_id, FieldValue.field_key == field_key
            )
        )
    ).scalar_one_or_none()
    if row is None or row.value is None:
        return None
    return Decimal(str(row.value))


async def _gather_base_scenario_inputs(
    db: AsyncSession,
    application: Application,
    purchase_price: Decimal,
    down_payment_pct: Decimal,
) -> ScenarioInputs:
    """Builds a `ScenarioInputs` from enriched `field_values` plus the LO's
    two owned inputs given here. `note_rate`/`discount_points_pct` are left
    at `0` -- every `Quote`'s `computed` is recomputed with that row's own
    rate/points (`inputs_with_priced_product`/AC10), never the scenario's base
    rate."""
    fico = await _field_decimal(db, application.id, "representative_fico")
    if fico is None:
        raise ValidationAppError("Cannot price: missing representative_fico.")

    tax_rate = await _field_decimal(db, application.id, "property_tax_annual_rate")
    if tax_rate is None:
        raise ValidationAppError("Cannot price: missing property_tax_annual_rate.")

    insurance_annual = await _field_decimal(db, application.id, "homeowners_ins_annual")
    if insurance_annual is None:
        raise ValidationAppError("Cannot price: missing homeowners_ins_annual.")
    # CQ-017 review round: money math lives only in `quote_engine`
    # (AGENTS.md); this was dividing inline.
    #
    # PR review round (fresh stage-6, PR #9): `insurance_annual_rate_from_
    # amount` raises `NonPositivePriceError` (a plain `ValueError`) for a
    # non-positive `purchase_price` -- nothing upstream of this function
    # catches bare `ValueError`s, so left alone that surfaced as a generic
    # 500 instead of the clean 422 every other "can't price" guard in this
    # function returns. `requested_price` has no DB check constraint
    # preventing 0/negative, so this is reachable.
    try:
        insurance_rate = insurance_annual_rate_from_amount(purchase_price, insurance_annual)
    except NonPositivePriceError as exc:
        raise ValidationAppError(f"Cannot price: {exc}") from exc

    hoa_monthly = await _field_decimal(db, application.id, "hoa_fee_monthly") or Decimal("0")

    strategy = _strategy_type(application)
    market_rent_ltr: Decimal | None = None
    str_gross_annual_revenue: Decimal | None = None
    if strategy is StrategyType.LTR:
        market_rent_ltr = await _field_decimal(db, application.id, "market_rent_ltr")
        if market_rent_ltr is None:
            raise ValidationAppError("Cannot price: missing market_rent_ltr.")
    elif strategy is StrategyType.STR:
        str_gross_annual_revenue = await _field_decimal(
            db, application.id, "gross_annual_revenue_str"
        )
        if str_gross_annual_revenue is None:
            raise ValidationAppError("Cannot price: missing gross_annual_revenue_str.")

    return ScenarioInputs(
        purchase_price=purchase_price,
        down_payment_pct=down_payment_pct,
        note_rate=Decimal("0"),
        strategy=strategy,
        fico=int(fico),
        property_tax_annual_rate=tax_rate,
        insurance_annual_rate=insurance_rate,
        hoa_monthly=hoa_monthly,
        market_rent_ltr=market_rent_ltr,
        str_gross_annual_revenue=str_gross_annual_revenue,
    )


async def _get_products(
    db: AsyncSession, application_id: uuid.UUID, overrides: ObRequestOverrides
) -> list[PricedProductDTO]:
    request = await build_ob_search_request(db, application_id, overrides)
    return await MockPricingClient(db).get_priced_products(request)


def _json_safe(model: ScenarioInputs | ConfigSnapshot | QuoteComputation) -> dict:
    return json.loads(model.model_dump_json())


async def _persist_scenario(
    db: AsyncSession,
    application_id: uuid.UUID,
    inputs: ScenarioInputs,
    config: ConfigSnapshot,
    dscr_bucket: DSCRBucket | None,
    prepayment_penalty_years: int | None = None,
) -> Scenario:
    inputs_json = _json_safe(inputs)
    if prepayment_penalty_years is not None:
        inputs_json["prepayment_penalty_years"] = prepayment_penalty_years
    scenario = Scenario(
        application_id=application_id,
        inputs=inputs_json,
        config_snapshot=_json_safe(config),
        dscr_bucket=dscr_bucket.value if dscr_bucket is not None else None,
    )
    db.add(scenario)
    await db.flush()
    return scenario


async def _persist_quote(
    db: AsyncSession,
    scenario_id: uuid.UUID,
    product: PricedProductDTO,
    computation: QuoteComputation,
    label: str,
) -> Quote:
    quote = Quote(
        scenario_id=scenario_id,
        investor=product.investor_name,
        product=product.product_name,
        rate=product.note_rate,
        points=product.discount_points_pct,
        lock_days=product.lock_period_days,
        computed=_json_safe(computation),
        label=label,
        priced_at=datetime.now(UTC),
    )
    db.add(quote)
    await db.flush()
    return quote


def _scenario_inputs_from_row(scenario: Scenario) -> ScenarioInputs:
    assert isinstance(scenario.inputs, dict)
    return ScenarioInputs.model_validate(scenario.inputs)


def _config_from_row(scenario: Scenario) -> ConfigSnapshot:
    assert isinstance(scenario.config_snapshot, dict)
    return ConfigSnapshot.model_validate(scenario.config_snapshot)


def _ob_overrides_from_scenario(scenario: Scenario, inputs: ScenarioInputs) -> ObRequestOverrides:
    ppp_years = None
    if isinstance(scenario.inputs, dict):
        ppp_years = scenario.inputs.get("prepayment_penalty_years")
    dscr = (
        ASSUMED_DSCR_BY_BUCKET[DSCRBucket(scenario.dscr_bucket)]
        if scenario.dscr_bucket is not None
        else None
    )
    lock_days = None
    if isinstance(scenario.inputs, dict):
        lock_days = scenario.inputs.get("lock_days")
    if lock_days is None:
        return ObRequestOverrides(
            down_payment_pct=inputs.down_payment_pct,
            dscr=dscr,
            prepayment_penalty_years=ppp_years,
        )
    # CQ-018: the overlay's lock days (pipeline-created scenarios have
    # none -> the OB request's 30-day default above).
    return ObRequestOverrides(
        down_payment_pct=inputs.down_payment_pct,
        dscr=dscr,
        prepayment_penalty_years=ppp_years,
        desired_lock_days=int(lock_days),
    )


async def get_scenario(db: AsyncSession, scenario_id: uuid.UUID) -> Scenario:
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise NotFoundError(f"Scenario not found: {scenario_id}")
    return scenario


async def get_priced_products_for_scenario(
    db: AsyncSession, scenario_id: uuid.UUID
) -> list[PricedProductDTO]:
    """`GET /scenarios/{id}/products`: the "Choose manually" grid."""
    scenario = await get_scenario(db, scenario_id)
    inputs = _scenario_inputs_from_row(scenario)
    overrides = _ob_overrides_from_scenario(scenario, inputs)
    return await _get_products(db, scenario.application_id, overrides)


async def create_scenario(
    db: AsyncSession,
    application_id: uuid.UUID,
    purchase_price: Decimal,
    down_payment_pct: Decimal,
    strategy: StrategyType,
    prepayment_penalty_years: int | None = None,
) -> Scenario:
    """The Quote Builder's Add/Edit overlay. Persists the scenario shell and
    (LTR/STR only) resolves `dscr_bucket` via the two-pass loop; it does not
    create `Quote` rows -- those come from `/autoquote` or manual `/quotes`
    (plan.md Decision 10)."""
    application = await _get_application(db, application_id)
    if _strategy_type(application) is not strategy:
        raise ValidationAppError(
            f"Scenario strategy {strategy} does not match application "
            f"occupancy/strategy ({application.occupancy}/{application.strategy})."
        )

    config = ConfigSnapshot()
    base_inputs = await _gather_base_scenario_inputs(
        db, application, purchase_price, down_payment_pct
    )

    dscr_bucket: DSCRBucket | None = None
    if strategy is not StrategyType.PRIMARY:

        async def _price_par(dscr_value: Decimal) -> PricedProductDTO:
            overrides = ObRequestOverrides(
                down_payment_pct=down_payment_pct,
                dscr=dscr_value,
                prepayment_penalty_years=prepayment_penalty_years,
            )
            products = await _get_products(db, application_id, overrides)
            par, _buydown = select_par_and_buydown(products)
            return par

        result = await run_two_pass_dscr(db, application_id, base_inputs, config, _price_par)
        dscr_bucket = result.computation.dscr_bucket

    scenario = await _persist_scenario(
        db, application_id, base_inputs, config, dscr_bucket, prepayment_penalty_years
    )
    await db.commit()
    return scenario


async def autoquote_scenario(
    db: AsyncSession, scenario_id: uuid.UUID
) -> tuple[Quote, Quote | None]:
    """`POST /scenarios/{id}/autoquote` -- Save & AutoQuote."""
    scenario = await get_scenario(db, scenario_id)
    inputs = _scenario_inputs_from_row(scenario)
    config = _config_from_row(scenario)
    products = await get_priced_products_for_scenario(db, scenario_id)
    par, buydown = select_par_and_buydown(products)

    par_quote = await _persist_quote(
        db, scenario.id, par, compute_quote(inputs_with_priced_product(inputs, par), config), "Par"
    )
    buydown_quote = None
    if buydown is not None:
        buydown_quote = await _persist_quote(
            db,
            scenario.id,
            buydown,
            compute_quote(inputs_with_priced_product(inputs, buydown), config),
            "Buydown",
        )
    await db.commit()
    return par_quote, buydown_quote


async def create_manual_quote(
    db: AsyncSession, scenario_id: uuid.UUID, product: PricedProductDTO, label: str
) -> Quote:
    """`POST /scenarios/{id}/quotes` -- "Choose manually" pick (AC10)."""
    scenario = await get_scenario(db, scenario_id)
    inputs = _scenario_inputs_from_row(scenario)
    config = _config_from_row(scenario)
    computation = compute_quote(inputs_with_priced_product(inputs, product), config)
    quote = await _persist_quote(db, scenario.id, product, computation, label)
    await db.commit()
    return quote


async def _price_group(
    db: AsyncSession,
    application_id: uuid.UUID,
    base_inputs: ScenarioInputs,
    config: ConfigSnapshot,
    overrides: ObRequestOverrides,
    dscr_bucket: DSCRBucket | None,
    prepayment_penalty_years: int | None,
) -> ScenarioGroupResult:
    products = await _get_products(db, application_id, overrides)
    par, buydown = select_par_and_buydown(products)
    scenario = await _persist_scenario(
        db, application_id, base_inputs, config, dscr_bucket, prepayment_penalty_years
    )
    quote_ids = [
        (
            await _persist_quote(
                db,
                scenario.id,
                par,
                compute_quote(inputs_with_priced_product(base_inputs, par), config),
                "Par",
            )
        ).id
    ]
    if buydown is not None:
        quote_ids.append(
            (
                await _persist_quote(
                    db,
                    scenario.id,
                    buydown,
                    compute_quote(inputs_with_priced_product(base_inputs, buydown), config),
                    "Buydown",
                )
            ).id
        )
    return ScenarioGroupResult(
        scenario_id=scenario.id, quote_ids=quote_ids, collapsed=False, note=None
    )


async def _create_default_scenarios_investment(
    db: AsyncSession,
    application: Application,
    config: ConfigSnapshot,
    down_payment_pct: Decimal,
    prepayment_penalty_years: int | None,
) -> DefaultScenarioSetResult:
    purchase_price = _purchase_price(application)
    base_inputs = await _gather_base_scenario_inputs(
        db, application, purchase_price, down_payment_pct
    )

    async def _price_par(dscr_value: Decimal) -> PricedProductDTO:
        overrides = ObRequestOverrides(
            down_payment_pct=down_payment_pct,
            dscr=dscr_value,
            prepayment_penalty_years=prepayment_penalty_years,
        )
        products = await _get_products(db, application.id, overrides)
        par, _buydown = select_par_and_buydown(products)
        return par

    # Group A: assumed DSCR bucket ONE_TO_1_25 (DSCR=1.00 sent to OB).
    group_a_overrides = ObRequestOverrides(
        down_payment_pct=down_payment_pct,
        dscr=ASSUMED_DSCR_BY_BUCKET[DSCRBucket.ONE_TO_1_25],
        prepayment_penalty_years=prepayment_penalty_years,
    )
    products_a = await _get_products(db, application.id, group_a_overrides)
    par_a, buydown_a = select_par_and_buydown(products_a)
    actual_computation = compute_quote(inputs_with_priced_product(base_inputs, par_a), config)
    actual_bucket = actual_computation.dscr_bucket
    assert actual_bucket is not None

    scenario_a = await _persist_scenario(
        db, application.id, base_inputs, config, DSCRBucket.ONE_TO_1_25, prepayment_penalty_years
    )
    quote_ids_a = [(await _persist_quote(db, scenario_a.id, par_a, actual_computation, "Par")).id]
    if buydown_a is not None:
        quote_ids_a.append(
            (
                await _persist_quote(
                    db,
                    scenario_a.id,
                    buydown_a,
                    compute_quote(inputs_with_priced_product(base_inputs, buydown_a), config),
                    "Buydown",
                )
            ).id
        )

    if actual_bucket == DSCRBucket.ONE_TO_1_25:
        group_a = ScenarioGroupResult(
            scenario_id=scenario_a.id,
            quote_ids=quote_ids_a,
            collapsed=True,
            note="same pricing tier as the 1.00 assumption",
        )
        return DefaultScenarioSetResult(groups=[group_a])

    group_a = ScenarioGroupResult(
        scenario_id=scenario_a.id, quote_ids=quote_ids_a, collapsed=False, note=None
    )

    two_pass = await run_two_pass_dscr(
        db, application.id, base_inputs, config, _price_par, assumed_bucket=actual_bucket
    )
    # Re-fetch the full grid at exactly the DSCR value that produced the
    # *kept* par, so the buydown row comes from the same rate-sheet pull.
    group_b_overrides = ObRequestOverrides(
        down_payment_pct=down_payment_pct,
        dscr=two_pass.priced_at_dscr,
        prepayment_penalty_years=prepayment_penalty_years,
    )
    products_b = await _get_products(db, application.id, group_b_overrides)
    _par_b_recheck, buydown_b = select_par_and_buydown(products_b)
    scenario_b = await _persist_scenario(
        db,
        application.id,
        base_inputs,
        config,
        two_pass.computation.dscr_bucket,
        prepayment_penalty_years,
    )
    quote_ids_b = [
        (
            await _persist_quote(
                db, scenario_b.id, two_pass.par_product, two_pass.computation, "Par"
            )
        ).id
    ]
    if buydown_b is not None:
        quote_ids_b.append(
            (
                await _persist_quote(
                    db,
                    scenario_b.id,
                    buydown_b,
                    compute_quote(inputs_with_priced_product(base_inputs, buydown_b), config),
                    "Buydown",
                )
            ).id
        )
    group_b = ScenarioGroupResult(
        scenario_id=scenario_b.id, quote_ids=quote_ids_b, collapsed=False, note=None
    )
    return DefaultScenarioSetResult(groups=[group_a, group_b])


async def _create_default_scenarios_primary(
    db: AsyncSession,
    application: Application,
    config: ConfigSnapshot,
    down_payment_pct: Decimal,
) -> DefaultScenarioSetResult:
    purchase_price = _purchase_price(application)
    base_inputs = await _gather_base_scenario_inputs(
        db, application, purchase_price, down_payment_pct
    )
    group_a = await _price_group(
        db,
        application.id,
        base_inputs,
        config,
        ObRequestOverrides(down_payment_pct=down_payment_pct),
        dscr_bucket=None,
        prepayment_penalty_years=None,
    )
    groups = [group_a]

    if down_payment_pct < _MI_REMOVAL_DOWN_PAYMENT:
        b_inputs = base_inputs.model_copy(update={"down_payment_pct": _MI_REMOVAL_DOWN_PAYMENT})
        products_b = await _get_products(
            db, application.id, ObRequestOverrides(down_payment_pct=_MI_REMOVAL_DOWN_PAYMENT)
        )
        par_b, _buydown_b = select_par_and_buydown(products_b)
        scenario_b = await _persist_scenario(db, application.id, b_inputs, config, None)
        quote_id_b = (
            await _persist_quote(
                db,
                scenario_b.id,
                par_b,
                compute_quote(inputs_with_priced_product(b_inputs, par_b), config),
                "Par",
            )
        ).id
        groups.append(
            ScenarioGroupResult(
                scenario_id=scenario_b.id, quote_ids=[quote_id_b], collapsed=False, note=None
            )
        )

    return DefaultScenarioSetResult(groups=groups)


async def create_default_scenarios(
    db: AsyncSession,
    application_id: uuid.UUID,
    down_payment_pct: Decimal | None = None,
    prepayment_penalty_years: int | None = None,
) -> DefaultScenarioSetResult:
    """The Quote Builder's default scenario sets (spec.md). `down_payment_pct`
    defaults to system-design's stated default per occupancy (20% primary,
    25% investment) when not given -- `auto_price` never passes one; the
    Quote Builder UI (CQ-017/18, out of scope here) may re-invoke this with
    the LO's chosen down payment."""
    application = await _get_application(db, application_id)
    config = ConfigSnapshot()
    if down_payment_pct is None:
        # CQ-018 (plan.md Decision 3): the LOS file's requested down
        # payment, written by `import_from_los`, when the loan file had one.
        down_payment_pct = await _field_decimal(db, application_id, "down_payment_pct")

    if application.occupancy is Occupancy.PRIMARY:
        resolved_down_payment = (
            down_payment_pct if down_payment_pct is not None else _DEFAULT_DOWN_PAYMENT_PRIMARY
        )
        result = await _create_default_scenarios_primary(
            db, application, config, resolved_down_payment
        )
    else:
        resolved_down_payment = (
            down_payment_pct if down_payment_pct is not None else _DEFAULT_DOWN_PAYMENT_INVESTMENT
        )
        resolved_ppp = prepayment_penalty_years if prepayment_penalty_years is not None else 5
        result = await _create_default_scenarios_investment(
            db, application, config, resolved_down_payment, resolved_ppp
        )

    await db.commit()
    return result


async def auto_price(db: AsyncSession, application_id: uuid.UUID) -> PricingResult:
    """CQ-011's `auto_price_application` activity / CQ-010's `demo-reset`
    entry point: prices the default scenario set at system-design's default
    inputs and returns every `scenario`/`quote` id it created."""
    result = await create_default_scenarios(db, application_id)
    return result.as_pricing_result()


# --- CQ-018 additions: public helpers the Quote Builder routes use --------


SCENARIO_EXTRA_INPUT_KEYS = ("prepayment_penalty_years", "lock_days")
"""LO-owned inputs stored beside `ScenarioInputs` in `scenarios.inputs`."""


def scenario_inputs(scenario: Scenario) -> ScenarioInputs:
    return _scenario_inputs_from_row(scenario)


async def rebuild_scenario_inputs(
    db: AsyncSession,
    scenario: Scenario,
    *,
    purchase_price: Decimal | None = None,
    down_payment_pct: Decimal | None = None,
    extras: dict[str, object] | None = None,
) -> ScenarioInputs:
    """Re-reads every enrichment-owned input (FICO, tax, insurance, HOA,
    rent/STR revenue) from `field_values` and keeps the scenario's own
    LO-owned inputs (price, down payment, PPP, lock days) unless new ones
    are given. Writes the result back to `scenario.inputs` (flush only)."""
    application = await _get_application(db, scenario.application_id)
    current = _scenario_inputs_from_row(scenario)
    base = await _gather_base_scenario_inputs(
        db,
        application,
        purchase_price if purchase_price is not None else current.purchase_price,
        down_payment_pct if down_payment_pct is not None else current.down_payment_pct,
    )
    old = scenario.inputs if isinstance(scenario.inputs, dict) else {}
    kept = {key: old[key] for key in SCENARIO_EXTRA_INPUT_KEYS if key in old}
    scenario.inputs = {**_json_safe(base), **kept, **(extras or {})}
    await db.flush()
    return base


def compute_for_product(scenario: Scenario, product: PricedProductDTO) -> QuoteComputation:
    return compute_quote(
        inputs_with_priced_product(_scenario_inputs_from_row(scenario), product),
        _config_from_row(scenario),
    )


async def persist_quote(
    db: AsyncSession, scenario: Scenario, product: PricedProductDTO, label: str
) -> Quote:
    return await _persist_quote(
        db, scenario.id, product, compute_for_product(scenario, product), label
    )


def computation_json(computation: QuoteComputation) -> dict:
    return _json_safe(computation)
