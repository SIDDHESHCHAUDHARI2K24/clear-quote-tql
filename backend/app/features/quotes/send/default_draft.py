"""The default draft package rule and the pre-drafted recommendation text
(CQ-019 plan.md Decisions 5 and 6).

`default_package_selection` is the single rule for "which quotes go to the
borrower by default": the Send tab's first GET and the seed's
`apply_send_fixture` both call it. It reuses CQ-018's
`list_application_scenarios` ordering (groups in canonical order, then Par,
Buydown, Manual within a group) instead of re-deriving it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import Application
from app.features.pricing.engine.types import ScenarioInputs, StrategyType
from app.features.pricing.scenarios.models import Scenario
from app.features.quotes.builder.models import Quote
from app.features.quotes.builder.service import list_application_scenarios
from app.features.quotes.send.view_model import ppp_years

MAX_PACKAGE_QUOTES = 3
"""The recommended quote plus up to 2 alternatives (spec Scope; catalog
§10 "Compares up to 3 options")."""


@dataclass(frozen=True)
class PackageSelection:
    quote_ids: list[uuid.UUID]
    recommended_quote_id: uuid.UUID | None


async def default_package_selection(db: AsyncSession, application: Application) -> PackageSelection:
    """The recommended quote (`applications.recommended_quote_id`), else the
    first group's Par (else its first card), then the remaining cards in
    group order, up to `MAX_PACKAGE_QUOTES` in total."""
    view = await list_application_scenarios(db, application)
    cards = [card.id for group in view.groups for card in group.quotes]
    if not cards:
        return PackageSelection(quote_ids=[], recommended_quote_id=None)

    recommended = application.recommended_quote_id
    if recommended not in cards:
        first_group = next(group for group in view.groups if group.quotes)
        recommended = next(
            (card.id for card in first_group.quotes if card.label == "Par"),
            first_group.quotes[0].id,
        )
    alternatives = [card for card in cards if card != recommended]
    return PackageSelection(
        quote_ids=[recommended, *alternatives[: MAX_PACKAGE_QUOTES - 1]],
        recommended_quote_id=recommended,
    )


_PRICING_TYPE = {"Par": "Par pricing", "Buydown": "Buydown pricing"}
_WHY = {
    "Par": "It balances your monthly payment and cash needed at closing.",
    "Buydown": "It lowers your rate and monthly payment for points paid at closing.",
}
_WHY_MANUAL = "It is the product your loan officer picked for your goals."


def _pct_label(fraction: Decimal) -> str:
    """`0.20` -> `"20"`, `0.125` -> `"12.5"` (display scaling only)."""
    text = str((fraction * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return text.rstrip("0").rstrip(".") if "." in text else text


def draft_recommendation_text(quote: Quote, scenario: Scenario, strategy: StrategyType) -> str:
    """e.g. "20% down · Par pricing at 7.500%, no prepay. It balances your
    monthly payment and cash needed at closing." Primary loans never mention
    a prepayment penalty (AGENTS.md)."""
    down = _pct_label(ScenarioInputs.model_validate(scenario.inputs).down_payment_pct)
    pricing = _PRICING_TYPE.get(quote.label, "Manual pricing")
    rate = quote.rate.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    prepay = ""
    years = ppp_years(strategy, scenario)
    if strategy is not StrategyType.PRIMARY:
        prepay = f", {years}-year prepay" if years else ", no prepay"
    why = _WHY.get(quote.label, _WHY_MANUAL)
    return f"{down}% down · {pricing} at {rate}%{prepay}. {why}"
