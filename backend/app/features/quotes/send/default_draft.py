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

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.models import Application
from app.features.quotes.builder.service import list_application_scenarios
from app.features.quotes.send.view_model import draft_recommendation_text

__all__ = ["MAX_PACKAGE_QUOTES", "default_package_selection", "draft_recommendation_text"]

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
