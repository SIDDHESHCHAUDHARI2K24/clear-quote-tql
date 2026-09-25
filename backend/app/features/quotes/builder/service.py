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
from app.features.applications.locks import lock_application
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.auth.models import User
from app.features.pricing.engine.quote_engine import discount_points_percent
from app.features.pricing.engine.types import DSCRBucket
from app.features.pricing.scenarios.models import Scenario
from app.features.pricing.scenarios.ob_request import (
    DEFAULT_INVESTMENT_PPP_YEARS,
    ObRequestOverrides,
    build_ob_search_request,
)
from app.features.pricing.scenarios.service import (
    NoEligibleProductsError,
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
    """Investment only. `None` means the scenario never set one, so it was
    priced at OB's 5-year default; only an explicit `0` is no penalty."""
    if years is None:
        years = DEFAULT_INVESTMENT_PPP_YEARS
    if years == 0:
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


def _collapsed_group_id(
    groups: list[tuple[Scenario, list[Quote]]], is_primary: bool
) -> uuid.UUID | None:
    """Investment only: the pipeline's collapsed group -- its default set
    had a single scenario, priced at the assumed 1.00 bucket, whose actual
    DSCR lands in the same bucket (`_create_default_scenarios_investment`).

    The pipeline creates its default set in one transaction, so the set is
    the scenarios sharing the earliest `created_at`. Tying the note to that
    group (not to "the app has one group") keeps it when the LO adds a
    scenario (CQ-018 PR review, minor 7)."""
    if is_primary or not groups:
        return None
    first_batch_at = min(scenario.created_at for scenario, _ in groups)
    batch = [(s, qs) for s, qs in groups if s.created_at == first_batch_at]
    if len(batch) != 1:
        return None
    scenario, quotes = batch[0]
    if scenario.dscr_bucket != DSCRBucket.ONE_TO_1_25.value:
        return None
    anchor = _par_or_first(quotes)
    if anchor is None or not isinstance(anchor.computed, dict):
        return None
    if anchor.computed.get("dscr_bucket") == DSCRBucket.ONE_TO_1_25.value:
        return scenario.id
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
    collapsed_id = _collapsed_group_id(groups, is_primary)
    return ApplicationScenariosRead(
        application_id=application.id,
        strategy=strategy,
        recommended_quote_id=application.recommended_quote_id,
        groups=[
            _group_read(
                s,
                qs,
                is_primary,
                strategy,
                application.recommended_quote_id,
                SAME_BUCKET_NOTE if s.id == collapsed_id else None,
            )
            for s, qs in groups
        ],
    )


async def get_scenario_group(db: AsyncSession, scenario_id: uuid.UUID) -> ScenarioGroupRead:
    scenario = await get_scenario(db, scenario_id)
    application = await db.get(Application, scenario.application_id)
    assert application is not None
    strategy = application_strategy(application)
    is_primary = strategy == "PRIMARY"
    all_groups = await _scenarios_with_quotes(db, application.id)
    quotes = next(qs for s, qs in all_groups if s.id == scenario_id)
    return _group_read(
        scenario,
        quotes,
        is_primary,
        strategy,
        application.recommended_quote_id,
        SAME_BUCKET_NOTE if _collapsed_group_id(all_groups, is_primary) == scenario_id else None,
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
    until Save & AutoQuote replaces them -- but only when the stored inputs
    actually changed (PR review, minor 2).

    Validates before anything is committed: missing OB fields (422
    `missing_field`), investment-only fields on a primary scenario (422
    naming the field), and an empty grid at the new inputs (422
    `no_eligible_products`, M2) all leave the scenario and its quotes as
    they were."""
    scenario = await get_scenario(db, scenario_id)
    application = await lock_application(db, scenario.application_id)
    await ensure_priceable(db, application.id, request.down_payment_pct)
    is_primary = application_strategy(application) == "PRIMARY"
    if is_primary and request.dscr_bucket is not None:
        raise ValidationAppError(
            "The assumed DSCR bucket applies to investment scenarios only.",
            details={"field": "dscr_bucket"},
        )
    if is_primary and request.prepayment_penalty_years is not None:
        raise ValidationAppError(
            "A prepayment penalty applies to investment scenarios only.",
            details={"field": "prepayment_penalty_years"},
        )

    before = _stored_inputs(scenario, is_primary)
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
    await _price_or_rollback(db, scenario)

    if _stored_inputs(scenario, is_primary) != before:
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


def _stored_inputs(scenario: Scenario, is_primary: bool) -> tuple[object, ...]:
    """What a PUT can change, normalized: the engine inputs (Decimals, so
    `0.2 == 0.20`), lock days (unset == the 30-day default), PPP (unset ==
    OB's 5-year investment default) and the assumed DSCR bucket."""
    extras = _inputs_json(scenario)
    lock_days = int(extras.get("lock_days") or _DEFAULT_LOCK_DAYS)
    ppp = extras.get("prepayment_penalty_years")
    if not is_primary and ppp is None:
        ppp = DEFAULT_INVESTMENT_PPP_YEARS
    return (scenario_inputs(scenario), lock_days, ppp, scenario.dscr_bucket)


async def _price_or_rollback(
    db: AsyncSession, scenario: Scenario
) -> tuple[list[PricedProductDTO], PricedProductDTO, PricedProductDTO | None]:
    """Prices the scenario at its (flushed) inputs. On a missing field or an
    empty grid, rolls back everything this request flushed and raises the
    422, so a failing write changes nothing (PR review M2)."""
    try:
        products = await get_priced_products_for_scenario(db, scenario.id)
        par, buydown = select_par_and_buydown(
            products, down_payment_pct=scenario_inputs(scenario).down_payment_pct
        )
    except PricingValidationError as exc:
        await db.rollback()
        raise missing_field_error(exc) from exc
    except NoEligibleProductsError:
        await db.rollback()
        raise
    return products, par, buydown


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
    """A *sent* package pins its quotes; an unsent draft (the Send tab's,
    CQ-019) never blocks a delete -- `_delete_quote_row` drops the quote
    from it instead (CQ-019 code review #2)."""
    stmt = select(QuotePackage.id).where(
        QuotePackage.sent_at.is_not(None),
        or_(
            QuotePackage.recommended_quote_id == quote_id,
            QuotePackage.quote_ids.contains([quote_id]),
        ),
    )
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None


@dataclass
class _RepriceOutcome:
    par: Quote
    buydown: Quote | None
    others: list[Quote]
    deleted_ids: list[uuid.UUID]
    recommendation_cleared: bool


async def _reprice_scenario(db: AsyncSession, scenario: Scenario) -> _RepriceOutcome:
    """Refresh inputs, price, then replace the Par/Buydown picks and
    re-price every other quote in the scenario. Pricing runs before any
    write to a quote, and a pricing failure (missing field, empty grid)
    rolls back everything the request flushed, so a failure leaves them
    untouched (plan.md Decision 4, PR review M2).

    The Par/Buydown rows are updated in place, not deleted and re-inserted,
    so their ids stay stable: the application's recommended quote and any
    quote package that names one keep pointing at the repriced row. A
    leftover auto quote is deleted; its id (and whether it was the
    recommendation) is reported so the caller can log it (minor 3).
    Flushes only; the caller commits."""
    await rebuild_scenario_inputs(db, scenario)
    products, par, buydown = await _price_or_rollback(db, scenario)
    deleted_ids: list[uuid.UUID] = []
    recommendation_cleared = False

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
            deleted_ids.append(quote.id)
            recommendation_cleared |= await _delete_quote_row(db, quote)
            continue
        fresh = next((row for row in products if _same_product(quote, row)), None)
        if fresh is None:
            # The product is no longer offered at these inputs: recompute
            # its engine output at the old rate/points so the card reflects
            # the new inputs, but keep it stale (not re-priced) -- code
            # review finding.
            quote.computed = computation_json(
                compute_for_product(scenario, _product_from_quote(quote))
            )
            quote.stale = True
            continue
        _apply_product(quote, scenario, fresh, now)
        others.append(quote)
    await db.flush()
    return _RepriceOutcome(
        par=par_quote,
        buydown=buydown_quote,
        others=others,
        deleted_ids=deleted_ids,
        recommendation_cleared=recommendation_cleared,
    )


async def _delete_quote_row(db: AsyncSession, quote: Quote) -> bool:
    """Deletes the quote; returns whether the application's recommendation
    was *cleared* by it -- `True` only when the deleted quote was the
    recommendation and nothing took its place. When the draft handed the
    recommendation to another quote (`drop_quote_from_drafts`), it moved,
    not cleared, and this returns `False` (CQ-020, PR #22 minor).

    Code review M4: `drop_quote_from_drafts` used to move the draft's
    recommendation to the quote left in its place while this function
    unconditionally cleared the application's -- the two disagreed. Now the
    application follows the draft's own new pick (or clears too, when there
    was no draft or nothing was left)."""
    application = (
        await db.execute(
            select(Application)
            .join(Scenario, Scenario.application_id == Application.id)
            .where(Scenario.id == quote.scenario_id)
        )
    ).scalar_one()
    from app.features.quotes.send.service import drop_quote_from_drafts

    followed = await drop_quote_from_drafts(db, quote.id)
    cleared = False
    if application.recommended_quote_id == quote.id:
        application.recommended_quote_id = (
            followed[1] if followed is not None and followed[0] == application.id else None
        )
        cleared = application.recommended_quote_id is None
        await db.flush()
    await db.delete(quote)
    await db.flush()
    return cleared


async def autoquote_replacing(
    db: AsyncSession, scenario_id: uuid.UUID, user: User
) -> tuple[Quote, Quote | None]:
    """`POST /scenarios/{id}/autoquote` (Save & AutoQuote): replaces the
    scenario's Par/Buydown with a fresh pick (spec AC3)."""
    scenario = await get_scenario(db, scenario_id)
    application = await lock_application(db, scenario.application_id)
    await ensure_priceable(db, application.id, scenario_inputs(scenario).down_payment_pct)
    outcome = await _reprice_scenario(db, scenario)
    par_quote, buydown_quote = outcome.par, outcome.buydown
    db.add(
        _event(
            application.id,
            user,
            "scenario.autoquoted",
            {
                "scenario_id": str(scenario.id),
                "quote_ids": [str(q.id) for q in (par_quote, buydown_quote) if q is not None],
                "deleted_quote_ids": [str(i) for i in outcome.deleted_ids],
                "recommendation_cleared": outcome.recommendation_cleared,
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
    await lock_application(db, application.id)
    await ensure_priceable(db, application.id)
    groups = await _scenarios_with_quotes(db, application.id)
    quote_ids: list[uuid.UUID] = []
    deleted_ids: list[uuid.UUID] = []
    recommendation_cleared = False
    for scenario, _quotes in groups:
        outcome = await _reprice_scenario(db, scenario)
        quote_ids.extend(
            q.id for q in (outcome.par, outcome.buydown, *outcome.others) if q is not None
        )
        deleted_ids.extend(outcome.deleted_ids)
        recommendation_cleared |= outcome.recommendation_cleared
    priced_at = datetime.now(UTC)
    db.add(
        _event(
            application.id,
            user,
            "quotes.repriced",
            {
                "scenario_ids": [str(s.id) for s, _ in groups],
                "quote_ids": [str(i) for i in quote_ids],
                "deleted_quote_ids": [str(i) for i in deleted_ids],
                "recommendation_cleared": recommendation_cleared,
            },
        )
    )
    await db.commit()
    return RepriceResponse(application_id=application.id, quote_ids=quote_ids, priced_at=priced_at)


async def _refetch_after_lock(db: AsyncSession, quote_id: uuid.UUID) -> Quote:
    """CQ-018 review n3 (fixed in CQ-019): a concurrent delete can commit
    between the scope check and the application lock, so re-read the quote
    once the lock is held and 404 when it is gone."""
    quote = await db.get(Quote, quote_id, populate_existing=True)
    if quote is None:
        raise NotFoundError(f"Quote not found: {quote_id}")
    return quote


async def recommend_quote(db: AsyncSession, quote: Quote, user: User) -> Application:
    """`POST /quotes/{id}/recommend`: one recommended quote per application
    (a single column, so setting it un-stars any other)."""
    scenario = await get_scenario(db, quote.scenario_id)
    application = await lock_application(db, scenario.application_id)
    quote = await _refetch_after_lock(db, quote.id)
    previous = application.recommended_quote_id
    application.recommended_quote_id = quote.id
    # CQ-019 (code review #4): the Send tab's unsent draft follows the star.
    from app.features.quotes.send.service import sync_draft_recommendation

    await sync_draft_recommendation(db, application.id, quote.id)
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
    409 only when a *sent* quote package names the quote -- deleting it
    would break that package's frozen snapshot and its `quotes.id` FK. An
    unsent draft never blocks the delete (nit, post-merge review; code
    review #2): the quote just leaves the draft (`drop_quote_from_drafts`)."""
    scenario = await get_scenario(db, quote.scenario_id)
    application = await lock_application(db, scenario.application_id)
    quote = await _refetch_after_lock(db, quote.id)
    if await _quote_in_package(db, quote.id):
        raise ConflictError("This quote is part of a quote package and can't be deleted.")
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
