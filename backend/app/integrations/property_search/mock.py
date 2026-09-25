"""`MockPropertySearchClient`: reads `provider_listings`.

Filters at 70-100% of the approved purchase price within the borrower's
buy-box states/metros (system-design.md's "Emulated integrations" table).
An empty result is a valid, non-error outcome.

**Decision** (plan.md #3): `deal_ranking_score` is a simple price-relative-
to-budget proxy (cheaper vs. the approved price ranks higher), not the
cashflow/DSCR ranking system-design.md's table describes. Real cashflow/
DSCR ranking needs `quote_engine` (money math lives only there, CQ-008) and
per-listing rent/STR-revenue data that `provider_listings` (CQ-007) doesn't
carry -- both out of this item's scope. CQ-023 (property matches) is where
that full ranking, if built, belongs.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common.errors import ProviderUnavailableError
from app.integrations.common.failure_toggle import is_forced_to_fail
from app.integrations.common.latency import simulate_latency
from app.integrations.common.logging import record_call
from app.integrations.property_search.models import ProviderListing
from app.integrations.property_search.schemas import PropertyMatchDTO, PropertySearchRequestDTO

ADAPTER = "property_search"

_FLOOR_MULTIPLIER = Decimal("0.70")
_CEILING_MULTIPLIER = Decimal("1.00")


def _format_baths(baths: Decimal) -> str:
    normalized = baths.normalize()
    return f"{normalized:f}" if normalized % 1 else f"{int(normalized)}"


class MockPropertySearchClient:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_matches(self, request: PropertySearchRequestDTO) -> list[PropertyMatchDTO]:
        latency_ms = await simulate_latency(ADAPTER)
        request_summary = {
            "approved_purchase_price": str(request.approved_purchase_price),
            "buy_box_states": request.buy_box_states,
            "buy_box_metros": request.buy_box_metros,
            "strategy": request.strategy.value,
        }

        if await is_forced_to_fail(ADAPTER):
            await record_call(
                self._session,
                ADAPTER,
                request_summary,
                success=False,
                latency_ms=latency_ms,
                error_code="PROVIDER_UNAVAILABLE",
            )
            raise ProviderUnavailableError(ADAPTER)

        floor_price = request.approved_purchase_price * _FLOOR_MULTIPLIER
        ceiling_price = request.approved_purchase_price * _CEILING_MULTIPLIER
        stmt = select(ProviderListing).where(
            ProviderListing.list_price >= floor_price,
            ProviderListing.list_price <= ceiling_price,
            ProviderListing.state.in_(request.buy_box_states),
            ProviderListing.metro.in_(request.buy_box_metros),
        )
        listings = (await self._session.execute(stmt)).scalars().all()

        matches = [
            PropertyMatchDTO(
                matched_property_id=str(listing.id),
                address=listing.address,
                city=listing.city,
                state=listing.state,
                zip=listing.zip,
                bed_bath_sqft=(
                    f"{listing.beds} bd · {_format_baths(listing.baths)} ba · {listing.sqft:,} sqft"
                ),
                deal_grade=listing.deal_grade,
                deal_ranking_score=(
                    Decimal("1") - (listing.list_price / request.approved_purchase_price)
                ).quantize(Decimal("0.0001")),
                tagline=listing.tagline,
                image_url=listing.image_url,
            )
            for listing in listings
        ]
        matches.sort(key=lambda match: match.deal_ranking_score, reverse=True)

        await record_call(
            self._session, ADAPTER, request_summary, success=True, latency_ms=latency_ms
        )
        return matches
