"""Quote Builder server side.

`draft_default_quote_set`: the exact function name CQ-011's `draft_quote_
set` activity calls to wrap up the automated pipeline's last stage.

Per plan.md Decision 11 (CQ-013): no new persisted "quote set"/recommendation
table is in CQ-007's model list -- `quote_packages.recommended_quote_id` is
the Send tab's job. `draft_default_quote_set`'s job is a thin confirmation:
it loads every `Quote` row `auto_price`'s `PricingResult` named (proving they
exist and belong to this application) and returns them as the drafted set.

CQ-018 adds the Quote Builder's read model (`list_application_scenarios`),
scenario edits, Save & AutoQuote's replace semantics, manual-quote delete,
the single recommended quote per application, and whole-application
reprice. Every money figure comes from `quote_engine` (`Quote.computed` or
a helper in `quote_engine`); this module only copies and scales for display.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import scope_applications
from app.core.enums import Occupancy, Strategy
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import User
from app.features.pricing.engine.quote_engine import discount_points_percent
from app.features.pricing.engine.types import DSCRBucket
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.ob_request import ObRequestOverrides, build_ob_search_request
from app.features.pricing.scenarios.service import (
    PricingResult,
    computation_json,
    compute_for_product,
    get_priced_products_for_scenario,
    get_scenario,
    persist_quote,
    rebuild_scenario_inputs,
    scenario_inputs,
    select_par_and_buydown,
)
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.schemas import (
    ApplicationScenariosRead,
    QuoteCardRead,
    RepriceResponse,
    ScenarioGroupRead,
    ScenarioInputsRead,
    ScenarioUpdateRequest,
)
from app.features.quotes.send.models import QuotePackage
from app.integrations.common.errors import PricingValidationError
from app.integrations.pricing.mock import ALWAYS_REQUIRED, CONDITIONALLY_REQUIRED_INVESTMENT
from app.integrations.pricing.schemas import PricedProductDTO

AUTO_LABELS = ("Par", "Buydown")
SAME_BUCKET_NOTE = "Your DSCR prices the same as 1.00"
_DEFAULT_LOCK_DAYS = 30
_PCT_2DP = Decimal("0.01")
_PCT_3DP = Decimal("0.001")

StrategyLiteral = Literal["PRIMARY", "LTR", "STR"]


@dataclass(frozen=True)
class QuoteSetResult:
    quote_ids: list[uuid.UUID]


async def draft_default_quote_set(
    db: AsyncSession, application_id: uuid.UUID, pricing_result: PricingResult
) -> QuoteSetResult:
    if not pricing_result.quote_ids:
        return QuoteSetResult(quote_ids=[])
    rows = (
        (
            await db.execute(
                select(Quote.id)
                .join(Scenario, Quote.scenario_id == Scenario.id)
                .where(
                    Scenario.application_id == application_id,
                    Quote.id.in_(pricing_result.quote_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return QuoteSetResult(quote_ids=list(rows))


# --- missing-field pre-check (AC6) ----------------------------------------

# The workspace tab that owns each OB-required field (plan.md Decision 6).
_OB_FIELD_TAB: dict[str, str] = {
    "Occupancy": "property",
    "PropertyType": "property",
    "NumberOfUnits": "property",
    "State": "property",
    "County": "property",
    "ZipCode": "property",
    "RepresentativeFICO": "credit",
}


def tab_for_ob_field(field: str) -> str:
    return _OB_FIELD_TAB.get(field, "pricing")


class MissingFieldError(ValidationAppError):
    """422 `{"error": {"code": "missing_field", "details": {"field", "tab",
    "missing_fields"}}}` -- the spec's `{code: "missing_field", field}`
    inside the app's pinned error envelope (plan.md Decision 6)."""

    def __init__(self, missing_fields: list[str]) -> None:
        field = missing_fields[0]
        super().__init__(
            f"Cannot price: missing {field}",
            code="missing_field",
            details={
                "field": field,
                "tab": tab_for_ob_field(field),
                "missing_fields": missing_fields,
            },
        )


def missing_field_error(exc: PricingValidationError) -> MissingFieldError:
    return MissingFieldError(exc.missing_fields)


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


async def ensure_priceable(
    db: AsyncSession,
    application_id: uuid.UUID,
    down_payment_pct: Decimal | None = None,
) -> None:
    """Raises `MissingFieldError` before any write when the OB request for
    this application would fail the adapter's required-field check."""
    request = await build_ob_search_request(
        db, application_id, ObRequestOverrides(down_payment_pct=down_payment_pct)
    )
    missing = [name for name in ALWAYS_REQUIRED if _is_missing(getattr(request, name))]
    if request.Occupancy == "InvestmentProperty":
        missing.extend(
            name
            for name in CONDITIONALLY_REQUIRED_INVESTMENT
            if _is_missing(getattr(request, name))
        )
    if missing:
        raise MissingFieldError(missing)


# --- scope ------------------------------------------------------------------


async def get_scoped_quote(db: AsyncSession, quote_id: uuid.UUID, user: User) -> Quote:
    """404 (Decision #11) unless the quote's application is in scope."""
    stmt = scope_applications(
        select(Application.id)
        .join(Scenario, Scenario.application_id == Application.id)
        .join(Quote, Quote.scenario_id == Scenario.id)
        .where(Quote.id == quote_id),
        user,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise NotFoundError(f"Quote not found: {quote_id}")
    quote = await db.get(Quote, quote_id)
    assert quote is not None
    return quote


# --- read model ---------------------------------------------------------------


def application_strategy(application: Application) -> StrategyLiteral | None:
    if application.occupancy is Occupancy.PRIMARY:
        return "PRIMARY"
    if application.occupancy is Occupancy.INVESTMENT:
        if application.strategy is Strategy.LTR:
            return "LTR"
        if application.strategy is Strategy.STR:
            return "STR"
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _pct_display(fraction: Decimal, step: Decimal) -> str:
    return str((fraction * Decimal("100")).quantize(step, rounding=ROUND_HALF_UP))


def _short_pct(fraction: Decimal) -> str:
    """`0.05` -> `"5"`, `0.125` -> `"12.5"` (group headings)."""
    text = _pct_display(fraction, _PCT_2DP)
    return text.rstrip("0").rstrip(".") if "." in text else text


def _prepay_label(years: int | None) -> str:
    if not years:
        return "No prepayment penalty"
    return f"{years}-year prepay"


def _inputs_json(scenario: Scenario) -> dict[str, Any]:
    return scenario.inputs if isinstance(scenario.inputs, dict) else {}


def _card(
    quote: Quote,
    scenario: Scenario,
    is_primary: bool,
    recommended_quote_id: uuid.UUID | None,
) -> QuoteCardRead:
    computed: dict[str, Any] = quote.computed if isinstance(quote.computed, dict) else {}
    loan = _decimal(computed.get("loan_amount")) or Decimal("0")
    points_amount = _decimal(computed.get("discount_points_amount")) or Decimal("0")
    points_pct = (
        discount_points_percent(loan, points_amount)
        if loan > 0
        else (quote.points * Decimal("100")).quantize(_PCT_3DP)
    )
    down_payment = (
        _decimal(computed.get("down_payment_pct")) or scenario_inputs(scenario).down_payment_pct
    )
    dscr = None if is_primary else _decimal(computed.get("dscr_ratio"))
    cashflow = None if is_primary else computed.get("monthly_cashflow")
    ppp = _inputs_json(scenario).get("prepayment_penalty_years")
    return QuoteCardRead(
        id=quote.id,
        scenario_id=quote.scenario_id,
        label=quote.label,
        investor=quote.investor,
        product=quote.product,
        rate_pct=str(quote.rate.quantize(_PCT_3DP)),
        points_pct=str(points_pct),
        points_amount=str(points_amount),
        note_rate=str((quote.rate / Decimal("100")).quantize(Decimal("0.00001"))),
        discount_points_pct=str((points_pct / Decimal("100")).quantize(Decimal("0.00001"))),
        lock_days=quote.lock_days,
        monthly_payment=str(computed.get("total_monthly_payment")),
        cash_to_close=str(computed.get("cash_to_close")),
        down_payment_pct=_pct_display(down_payment, _PCT_2DP),
        prepay_label=None if is_primary else _prepay_label(ppp),
        dscr_ratio=str(dscr.quantize(_PCT_2DP)) if dscr is not None else None,
        monthly_cashflow=str(cashflow) if cashflow is not None else None,
        priced_at=quote.priced_at,
        stale=quote.stale,
        recommended=quote.id == recommended_quote_id,
        computed=computed,
    )


def _par_or_first(quotes: list[Quote]) -> Quote | None:
    return next((q for q in quotes if q.label == "Par"), quotes[0] if quotes else None)


def _group_label(scenario: Scenario, quotes: list[Quote], is_primary: bool) -> str:
    inputs = scenario_inputs(scenario)
    if is_primary or scenario.dscr_bucket is None:
        return f"At {_short_pct(inputs.down_payment_pct)}% down"
    if scenario.dscr_bucket == DSCRBucket.ONE_TO_1_25.value:
        return "At DSCR 1.00"
    anchor = _par_or_first(quotes)
    computed = anchor.computed if anchor is not None and isinstance(anchor.computed, dict) else {}
    dscr = _decimal(computed.get("dscr_ratio"))
    if dscr is not None and computed.get("dscr_bucket") == scenario.dscr_bucket:
        return f"At your DSCR ({dscr.quantize(_PCT_2DP)})"
    if scenario.dscr_bucket == DSCRBucket.GE_1_25.value:
        return "At DSCR 1.25+"
    return "At DSCR below 1.00"


def _same_bucket_note(groups: list[tuple[Scenario, list[Quote]]], is_primary: bool) -> str | None:
    """Investment only: one group priced at the assumed 1.00 bucket whose
    actual DSCR lands in the same bucket (`_create_default_scenarios_
    investment`'s collapsed case)."""
    if is_primary or len(groups) != 1:
        return None
    scenario, quotes = groups[0]
    if scenario.dscr_bucket != DSCRBucket.ONE_TO_1_25.value:
        return None
    anchor = _par_or_first(quotes)
    if anchor is None or not isinstance(anchor.computed, dict):
        return None
    if anchor.computed.get("dscr_bucket") == DSCRBucket.ONE_TO_1_25.value:
        return SAME_BUCKET_NOTE
    return None


async def _scenarios_with_quotes(
    db: AsyncSession, application_id: uuid.UUID
) -> list[tuple[Scenario, list[Quote]]]:
    scenarios = (
        (
            await db.execute(
                select(Scenario)
                .where(Scenario.application_id == application_id)
                .order_by(Scenario.created_at, Scenario.id)
            )
        )
        .scalars()
        .all()
    )
    if not scenarios:
        return []
    quotes = (
        (
            await db.execute(
                select(Quote)
                .where(Quote.scenario_id.in_([s.id for s in scenarios]))
                .order_by(Quote.created_at, Quote.id)
            )
        )
        .scalars()
        .all()
    )
    by_scenario: dict[uuid.UUID, list[Quote]] = {s.id: [] for s in scenarios}
    for quote in quotes:
        by_scenario[quote.scenario_id].append(quote)
    order = {label: index for index, label in enumerate(AUTO_LABELS)}
    return [
        (s, sorted(by_scenario[s.id], key=lambda q: order.get(q.label, len(order))))
        for s in sorted(scenarios, key=_group_sort_key)
    ]


def _group_sort_key(scenario: Scenario) -> tuple[datetime, int, Decimal, str]:
    """The pipeline creates a default set in one transaction, so its
    scenarios share `created_at`: within that, the assumed DSCR 1.00 group
    comes first (investment) and a lower down payment first (primary)."""
    assumed_first = 0 if scenario.dscr_bucket in (None, DSCRBucket.ONE_TO_1_25.value) else 1
    return (
        scenario.created_at,
        assumed_first,
        scenario_inputs(scenario).down_payment_pct,
        str(scenario.id),
    )


def _group_read(
    scenario: Scenario,
    quotes: list[Quote],
    is_primary: bool,
    strategy: StrategyLiteral | None,
    recommended_quote_id: uuid.UUID | None,
    note: str | None,
) -> ScenarioGroupRead:
    inputs = scenario_inputs(scenario)
    extras = _inputs_json(scenario)
    return ScenarioGroupRead(
        id=scenario.id,
        label=_group_label(scenario, quotes, is_primary),
        note=note,
        dscr_bucket=DSCRBucket(scenario.dscr_bucket) if scenario.dscr_bucket else None,
        inputs=ScenarioInputsRead(
            purchase_price=str(inputs.purchase_price),
            down_payment_pct=str(inputs.down_payment_pct),
            prepayment_penalty_years=extras.get("prepayment_penalty_years"),
            lock_days=int(extras.get("lock_days") or _DEFAULT_LOCK_DAYS),
            fico=inputs.fico,
            strategy=strategy or inputs.strategy.value,
        ),
        engine_inputs=json.loads(inputs.model_dump_json()),
        quotes=[_card(q, scenario, is_primary, recommended_quote_id) for q in quotes],
        created_at=scenario.created_at,
    )


async def list_application_scenarios(
    db: AsyncSession, application: Application
) -> ApplicationScenariosRead:
    strategy = application_strategy(application)
    is_primary = strategy == "PRIMARY"
    groups = await _scenarios_with_quotes(db, application.id)
    note = _same_bucket_note(groups, is_primary)
    return ApplicationScenariosRead(
        application_id=application.id,
        strategy=strategy,
        recommended_quote_id=application.recommended_quote_id,
        groups=[
            _group_read(s, qs, is_primary, strategy, application.recommended_quote_id, note)
            for s, qs in groups
        ],
    )


async def get_scenario_group(db: AsyncSession, scenario_id: uuid.UUID) -> ScenarioGroupRead:
    scenario = await get_scenario(db, scenario_id)
    application = await db.get(Application, scenario.application_id)
    assert application is not None
    strategy = application_strategy(application)
    groups = [g for g in await _scenarios_with_quotes(db, application.id) if g[0].id == scenario_id]
    _s, quotes = groups[0]
    return _group_read(
        scenario,
        quotes,
        strategy == "PRIMARY",
        strategy,
        application.recommended_quote_id,
        None,
    )


# --- writes -------------------------------------------------------------------


def _event(application_id: uuid.UUID, user: User, type_: str, payload: dict) -> ActivityEvent:
    return ActivityEvent(
        application_id=application_id,
        actor=str(user.id),
        type=type_,
        payload=payload,
        at=datetime.now(UTC),
    )


async def update_scenario(
    db: AsyncSession, scenario_id: uuid.UUID, request: ScenarioUpdateRequest, user: User
) -> ScenarioGroupRead:
    """`PUT /scenarios/{id}`: persists the overlay's LO-owned inputs and
    re-reads enrichment-owned ones. Existing quotes stay (marked stale)
    until Save & AutoQuote replaces them."""
    scenario = await get_scenario(db, scenario_id)
    application = await db.get(Application, scenario.application_id)
    assert application is not None
    await ensure_priceable(db, application.id, request.down_payment_pct)
    is_primary = application_strategy(application) == "PRIMARY"
    if is_primary and request.dscr_bucket is not None:
        raise ValidationAppError("dscr_bucket applies to investment scenarios only.")

    extras: dict[str, object] = {"lock_days": request.lock_days}
    if not is_primary and request.prepayment_penalty_years is not None:
        extras["prepayment_penalty_years"] = request.prepayment_penalty_years
    await rebuild_scenario_inputs(
        db,
        scenario,
        purchase_price=request.purchase_price,
        down_payment_pct=request.down_payment_pct,
        extras=extras,
    )
    if request.dscr_bucket is not None:
        scenario.dscr_bucket = request.dscr_bucket.value
    await db.execute(update(Quote).where(Quote.scenario_id == scenario.id).values(stale=True))
    db.add(
        _event(
            application.id,
            user,
            "scenario.updated",
            {"scenario_id": str(scenario.id), "inputs": request.model_dump(mode="json")},
        )
    )
    await db.commit()
    return await get_scenario_group(db, scenario.id)


def _same_product(quote: Quote, row: PricedProductDTO) -> bool:
    return (
        row.investor_name == quote.investor
        and row.product_name == quote.product
        and row.lock_period_days == quote.lock_days
    )


def _product_from_quote(quote: Quote) -> PricedProductDTO:
    """A quote whose product left the grid: keep its rate/points (points at
    full precision from its own engine output, not the 3dp column)."""
    computed = quote.computed if isinstance(quote.computed, dict) else {}
    loan = _decimal(computed.get("loan_amount")) or Decimal("0")
    amount = _decimal(computed.get("discount_points_amount")) or Decimal("0")
    points_fraction = (
        discount_points_percent(loan, amount) / Decimal("100") if loan > 0 else quote.points
    )
    return PricedProductDTO(
        investor_name=quote.investor,
        product_name=quote.product,
        lock_period_days=quote.lock_days,
        note_rate=quote.rate,
        price_pct=Decimal("100"),  # unused by `compute_quote`
        discount_points_pct=points_fraction,
        discount_points_amount=amount,
        is_par_rate=False,
        is_buydown_rate=False,
    )


def _apply_product(
    quote: Quote, scenario: Scenario, product: PricedProductDTO, now: datetime
) -> None:
    quote.investor = product.investor_name
    quote.product = product.product_name
    quote.lock_days = product.lock_period_days
    quote.rate = product.note_rate
    quote.points = product.discount_points_pct
    quote.computed = computation_json(compute_for_product(scenario, product))
    quote.priced_at = now
    quote.stale = False


async def _quote_in_package(db: AsyncSession, quote_id: uuid.UUID) -> bool:
    stmt = select(QuotePackage.id).where(
        or_(
            QuotePackage.recommended_quote_id == quote_id,
            QuotePackage.quote_ids.contains([quote_id]),
        )
    )
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def _reprice_scenario(
    db: AsyncSession, scenario: Scenario
) -> tuple[Quote, Quote | None, list[Quote]]:
    """Refresh inputs, price, then replace the Par/Buydown picks and
    re-price every other quote in the scenario. Pricing runs before any
    write to a quote, so a failure leaves them untouched (plan.md
    Decision 4).

    The Par/Buydown rows are updated in place, not deleted and re-inserted,
    so their ids stay stable: the application's recommended quote and any
    quote package that names one keep pointing at the repriced row.
    Flushes only; the caller commits."""
    await rebuild_scenario_inputs(db, scenario)
    try:
        products = await get_priced_products_for_scenario(db, scenario.id)
    except PricingValidationError as exc:
        raise missing_field_error(exc) from exc
    par, buydown = select_par_and_buydown(products)

    existing = list(
        (
            await db.execute(
                select(Quote)
                .where(Quote.scenario_id == scenario.id)
                .order_by(Quote.created_at, Quote.id)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    old_par = next((q for q in existing if q.label == "Par"), None)
    old_buydown = next((q for q in existing if q.label == "Buydown"), None)

    if old_par is not None:
        _apply_product(old_par, scenario, par, now)
        par_quote = old_par
    else:
        par_quote = await persist_quote(db, scenario, par, "Par")

    buydown_quote: Quote | None = None
    if buydown is not None and old_buydown is not None:
        _apply_product(old_buydown, scenario, buydown, now)
        buydown_quote = old_buydown
    elif buydown is not None:
        buydown_quote = await persist_quote(db, scenario, buydown, "Buydown")

    others: list[Quote] = []
    for quote in existing:
        if quote is par_quote or quote is buydown_quote:
            continue
        if quote.label in AUTO_LABELS and not await _quote_in_package(db, quote.id):
            # A duplicate or no-longer-offered Par/Buydown: Save & AutoQuote
            # keeps exactly one of each (spec AC3).
            await _delete_quote_row(db, quote)
            continue
        fresh = next((row for row in products if _same_product(quote, row)), None)
        _apply_product(quote, scenario, fresh or _product_from_quote(quote), now)
        others.append(quote)
    await db.flush()
    return par_quote, buydown_quote, others


async def _delete_quote_row(db: AsyncSession, quote: Quote) -> None:
    application = (
        await db.execute(
            select(Application)
            .join(Scenario, Scenario.application_id == Application.id)
            .where(Scenario.id == quote.scenario_id)
        )
    ).scalar_one()
    if application.recommended_quote_id == quote.id:
        application.recommended_quote_id = None
        await db.flush()
    await db.delete(quote)
    await db.flush()


async def autoquote_replacing(
    db: AsyncSession, scenario_id: uuid.UUID, user: User
) -> tuple[Quote, Quote | None]:
    """`POST /scenarios/{id}/autoquote` (Save & AutoQuote): replaces the
    scenario's Par/Buydown with a fresh pick (spec AC3)."""
    scenario = await get_scenario(db, scenario_id)
    application = await db.get(Application, scenario.application_id)
    assert application is not None
    await ensure_priceable(db, application.id, scenario_inputs(scenario).down_payment_pct)
    par_quote, buydown_quote, _manual = await _reprice_scenario(db, scenario)
    db.add(
        _event(
            application.id,
            user,
            "scenario.autoquoted",
            {
                "scenario_id": str(scenario.id),
                "quote_ids": [str(q.id) for q in (par_quote, buydown_quote) if q is not None],
            },
        )
    )
    await db.commit()
    await db.refresh(par_quote)
    if buydown_quote is not None:
        await db.refresh(buydown_quote)
    return par_quote, buydown_quote


async def reprice_application(
    db: AsyncSession, application: Application, user: User
) -> RepriceResponse:
    """`POST /applications/{id}/reprice`: re-runs AutoQuote for every
    scenario (the stale banner's "Re-price"), clearing `stale` and bumping
    `priced_at` on every quote (AC8)."""
    await ensure_priceable(db, application.id)
    groups = await _scenarios_with_quotes(db, application.id)
    quote_ids: list[uuid.UUID] = []
    for scenario, _quotes in groups:
        par_quote, buydown_quote, manual = await _reprice_scenario(db, scenario)
        quote_ids.extend(q.id for q in (par_quote, buydown_quote, *manual) if q is not None)
    priced_at = datetime.now(UTC)
    db.add(
        _event(
            application.id,
            user,
            "quotes.repriced",
            {
                "scenario_ids": [str(s.id) for s, _ in groups],
                "quote_ids": [str(i) for i in quote_ids],
            },
        )
    )
    await db.commit()
    return RepriceResponse(application_id=application.id, quote_ids=quote_ids, priced_at=priced_at)


async def recommend_quote(db: AsyncSession, quote: Quote, user: User) -> Application:
    """`POST /quotes/{id}/recommend`: one recommended quote per application
    (a single column, so setting it un-stars any other)."""
    scenario = await get_scenario(db, quote.scenario_id)
    application = await db.get(Application, scenario.application_id)
    assert application is not None
    previous = application.recommended_quote_id
    application.recommended_quote_id = quote.id
    db.add(
        _event(
            application.id,
            user,
            "quote.recommended",
            {
                "quote_id": str(quote.id),
                "previous_quote_id": str(previous) if previous is not None else None,
                "rate": str(quote.rate),
                "label": quote.label,
            },
        )
    )
    await db.commit()
    return application


async def delete_quote(db: AsyncSession, quote: Quote, user: User) -> None:
    """`DELETE /quotes/{id}`: clears the recommendation when it pointed here.
    409 when a quote package (draft or sent) names the quote -- deleting it
    would break that package's snapshot and its `quotes.id` FK."""
    if await _quote_in_package(db, quote.id):
        raise ConflictError("This quote is part of a quote package and can't be deleted.")
    scenario = await get_scenario(db, quote.scenario_id)
    application = await db.get(Application, scenario.application_id)
    assert application is not None
    was_recommended = application.recommended_quote_id == quote.id
    db.add(
        _event(
            application.id,
            user,
            "quote.deleted",
            {
                "quote_id": str(quote.id),
                "label": quote.label,
                "rate": str(quote.rate),
                "was_recommended": was_recommended,
            },
        )
    )
    await _delete_quote_row(db, quote)
    await db.commit()
