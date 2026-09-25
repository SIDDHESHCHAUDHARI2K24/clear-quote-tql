"""Buy-box reference data: metros per state (CQ-028 plan.md #17)."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.features.reference.catalog import STATIC_METROS
from app.integrations.property_search.models import ProviderListing

_STATE = re.compile(r"^[A-Z]{2}$")


def normalize_states(states: list[str]) -> list[str]:
    """Upper-cases, de-duplicates (order kept) and validates state codes."""
    result: list[str] = []
    for raw in states:
        state = raw.strip().upper()
        if not state:
            continue
        if not _STATE.fullmatch(state):
            raise ValidationAppError(f"Not a 2-letter state code: {raw!r}")
        if state not in result:
            result.append(state)
    return result


async def metros_for_states(db: AsyncSession, states: list[str]) -> dict[str, list[str]]:
    """`state -> sorted metros`: the distinct `provider_listings.metro` for the
    state merged with the static catalog. Every requested state is a key
    (possibly with an empty list)."""
    result: dict[str, set[str]] = {state: set(STATIC_METROS.get(state, ())) for state in states}
    if states:
        rows = (
            await db.execute(
                select(ProviderListing.state, ProviderListing.metro)
                .where(ProviderListing.state.in_(states))
                .distinct()
            )
        ).all()
        for state, metro in rows:
            result[state].add(metro)
    return {state: sorted(metros) for state, metros in result.items()}


async def county_for_zip(db: AsyncSession, zip_code: str) -> str | None:
    """The mock zip -> county lookup (plan.md #16): the county the provider
    listings record for that zip, if any."""
    return (
        await db.execute(
            select(ProviderListing.county)
            .where(ProviderListing.zip == zip_code)
            .order_by(ProviderListing.county)
            .limit(1)
        )
    ).scalar_one_or_none()
