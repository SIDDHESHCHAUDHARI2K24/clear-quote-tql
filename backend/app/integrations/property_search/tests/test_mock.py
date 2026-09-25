"""AC2: `MockPropertySearchClient` conforms to `PropertySearchClient`, filters
70-100% of the approved price within the buy-box, and returns `[]` (not an
error) when nothing matches."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.applications.property.models import PropertyType
from app.integrations.property_search.mock import MockPropertySearchClient
from app.integrations.property_search.models import DealGrade, ProviderListing
from app.integrations.property_search.protocol import PropertySearchClient
from app.integrations.property_search.schemas import MatchStrategy, PropertySearchRequestDTO


def _listing(**overrides: object) -> ProviderListing:
    defaults: dict[str, object] = dict(
        address="4412 W Gray St",
        city="Tampa",
        state="FL",
        zip="33607",
        county="Hillsborough",
        metro="Tampa",
        list_price=Decimal("250000.00"),
        beds=4,
        baths=Decimal("2.0"),
        sqft=1710,
        property_type=PropertyType.SINGLE_FAMILY,
        image_url="https://example.com/listing.jpg",
        deal_grade=DealGrade.GREAT_BUY,
        tagline="12 min to theme-park corridor",
    )
    defaults.update(overrides)
    return ProviderListing(**defaults)  # type: ignore[arg-type]


async def test_mock_satisfies_protocol(db_session: AsyncSession) -> None:
    assert isinstance(MockPropertySearchClient(db_session), PropertySearchClient)


async def test_search_matches_filters_price_band_and_buy_box(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            _listing(list_price=Decimal("240000.00")),  # 80% of 300k -- in range
            _listing(list_price=Decimal("200000.00")),  # below 70% floor -- excluded
            _listing(list_price=Decimal("310000.00")),  # above ceiling -- excluded
            _listing(state="TX", metro="Austin", list_price=Decimal("250000.00")),  # wrong buy-box
        ]
    )
    await db_session.commit()

    matches = await MockPropertySearchClient(db_session).search_matches(
        PropertySearchRequestDTO(
            approved_purchase_price=Decimal("300000.00"),
            buy_box_states=["FL"],
            buy_box_metros=["Tampa"],
            strategy=MatchStrategy.LTR,
        )
    )

    assert len(matches) == 1
    assert matches[0].bed_bath_sqft == "4 bd · 2 ba · 1,710 sqft"


async def test_search_matches_empty_result_is_not_an_error(db_session: AsyncSession) -> None:
    matches = await MockPropertySearchClient(db_session).search_matches(
        PropertySearchRequestDTO(
            approved_purchase_price=Decimal("300000.00"),
            buy_box_states=["NC"],
            buy_box_metros=["Asheville"],
            strategy=MatchStrategy.STR,
        )
    )

    assert matches == []
