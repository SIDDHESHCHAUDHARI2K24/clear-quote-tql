"""AC5: the background generator produces 190-210 `applications` rows using
`random.Random(SEED_RNG_SEED)`, and running it twice with the same seed
produces identical per-status/per-LO counts -- the same guarantee two
`make demo-reset` runs need (each drops and recreates the DB first, so the
generator always starts from the same empty state; this test proves the
generator itself is the deterministic half of that story)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.auth.models import User
from seed.config import DEFAULT_SEED_RNG_SEED
from seed.generators.background_applications import seed_background_applications

_MARKETS = [
    {"city": "Tampa", "state": "FL", "zip": "33602", "county": "Hillsborough"},
    {"city": "Carmel", "state": "IN", "zip": "46032", "county": "Hamilton"},
    {"city": "Denver", "state": "CO", "zip": "80202", "county": "Denver"},
]


async def _make_two_los(db: AsyncSession) -> list:
    los = []
    for i in range(2):
        user = User(
            email=f"lo-{i}@clearquote-demo.test",
            password_hash="not-a-real-hash",
            role=UserRole.LO,
            full_name=f"Test LO {i}",
        )
        db.add(user)
        los.append(user)
    await db.flush()
    return [u.id for u in los]


async def test_default_seed_produces_190_to_210_rows(db_session: AsyncSession) -> None:
    lo_ids = await _make_two_los(db_session)

    summary = await seed_background_applications(
        db_session, rng_seed=DEFAULT_SEED_RNG_SEED, lo_ids=lo_ids, markets=_MARKETS
    )

    assert 190 <= summary.total_created <= 210


async def test_same_seed_produces_identical_status_and_lo_counts(db_session: AsyncSession) -> None:
    lo_ids = await _make_two_los(db_session)

    first = await seed_background_applications(
        db_session, rng_seed=DEFAULT_SEED_RNG_SEED, lo_ids=lo_ids, markets=_MARKETS, count=50
    )
    second = await seed_background_applications(
        db_session, rng_seed=DEFAULT_SEED_RNG_SEED, lo_ids=lo_ids, markets=_MARKETS, count=50
    )

    assert first.by_status == second.by_status
    assert first.by_lo == second.by_lo
    assert first.total_created == second.total_created == 50


async def test_different_seed_can_produce_different_status_counts(db_session: AsyncSession) -> None:
    lo_ids = await _make_two_los(db_session)

    first = await seed_background_applications(
        db_session, rng_seed=DEFAULT_SEED_RNG_SEED, lo_ids=lo_ids, markets=_MARKETS, count=50
    )
    second = await seed_background_applications(
        db_session, rng_seed=DEFAULT_SEED_RNG_SEED + 1, lo_ids=lo_ids, markets=_MARKETS, count=50
    )

    assert first.by_status != second.by_status or first.by_lo != second.by_lo
