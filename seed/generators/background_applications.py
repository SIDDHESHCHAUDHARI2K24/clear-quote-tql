"""Deterministic ~200-application background generator (spec.md scope item 4,
AC5, plan.md decision D4).

Draws only from the 10 persona markets (Decision D4 -- no extra `provider_*`
fixtures needed beyond AC3's), spreads across every `application_status`,
alternates the 2 seeded LOs, and mixes occupancy/strategy roughly 40%
Primary / 40% LTR / 20% STR. Every row's randomness comes from a single
`random.Random(SEED_RNG_SEED)` instance consumed in a fixed order, so two
runs with the same seed produce byte-identical per-status/per-LO counts
(AC5) -- this generator writes bare `applications`/`clients` rows only
(no parties/housing/etc.): it exists to make lists and the dashboard look
lived-in, not to be pipeline-complete like the 10 named personas.
"""

from __future__ import annotations

import random
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationStatus, Occupancy, Strategy
from app.features.applications.models import Application
from app.features.clients.models import Client

BACKGROUND_APPLICATION_COUNT = 200

_FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Taylor",
    "Morgan",
    "Casey",
    "Riley",
    "Jamie",
    "Cameron",
    "Drew",
    "Skyler",
    "Reese",
    "Quinn",
    "Avery",
    "Rowan",
    "Hayden",
    "Emerson",
    "Sawyer",
    "Finley",
    "Harper",
    "Peyton",
]
_LAST_NAMES = [
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
]

# (status, weight) -- roughly matches system-design.md's dashboard tile
# shape (a mix across every stage, weighted toward the common ones).
_STATUS_WEIGHTS: list[tuple[ApplicationStatus, int]] = [
    (ApplicationStatus.INTAKE, 15),
    (ApplicationStatus.VERIFYING, 15),
    (ApplicationStatus.NEEDS_ATTENTION, 10),
    (ApplicationStatus.READY_TO_PRICE, 15),
    (ApplicationStatus.PRICED, 30),
    (ApplicationStatus.SENT, 10),
    (ApplicationStatus.STALE, 5),
]

# (occupancy, strategy or None) -- ~40% Primary / 40% LTR / 20% STR.
_OCCUPANCY_WEIGHTS: list[tuple[Occupancy, Strategy | None, int]] = [
    (Occupancy.PRIMARY, None, 40),
    (Occupancy.INVESTMENT, Strategy.LTR, 40),
    (Occupancy.INVESTMENT, Strategy.STR, 20),
]


def _weighted_choice[T](rng: random.Random, options: list[tuple[T, int]]) -> T:
    total = sum(weight for _, weight in options)
    pick = rng.uniform(0, total)
    upto = 0.0
    for value, weight in options:
        upto += weight
        if pick <= upto:
            return value
    return options[-1][0]


@dataclass
class BackgroundSeedSummary:
    total_created: int
    by_status: dict[str, int]
    by_lo: dict[str, int]


async def seed_background_applications(
    db: AsyncSession,
    *,
    rng_seed: int,
    lo_ids: list[uuid.UUID],
    markets: list[dict[str, str]],
    count: int = BACKGROUND_APPLICATION_COUNT,
) -> BackgroundSeedSummary:
    """`markets` is CQ-010's 10 persona `{city, state, zip, county}` dicts
    (Decision D4); `lo_ids` is the 2 seeded LO users' ids, in a fixed order
    so `i % len(lo_ids)` alternation is itself deterministic."""
    rng = random.Random(rng_seed)
    now = datetime.now(UTC)

    status_counts: Counter[str] = Counter()
    lo_counts: Counter[str] = Counter()

    for i in range(count):
        first_name = rng.choice(_FIRST_NAMES)
        last_name = rng.choice(_LAST_NAMES)
        market = rng.choice(markets)
        occupancy, strategy = _weighted_choice(
            rng, [((occ, strat), w) for occ, strat, w in _OCCUPANCY_WEIGHTS]
        )
        status = _weighted_choice(rng, _STATUS_WEIGHTS)
        price = Decimal(rng.randrange(180_000, 650_000, 5_000))
        days_ago = rng.randint(0, 120)
        lo_id = lo_ids[i % len(lo_ids)]

        client = Client(
            full_name=f"{first_name} {last_name}",
            email=f"bg-{i:04d}-{first_name.lower()}.{last_name.lower()}@clearquote-demo.test",
            assigned_lo_id=lo_id,
        )
        db.add(client)
        await db.flush()

        application = Application(
            client_id=client.id,
            lo_id=lo_id,
            occupancy=occupancy,
            strategy=strategy,
            requested_price=price,
            subject_state=market["state"],
            status=status,
            created_at=now - timedelta(days=days_ago),
        )
        db.add(application)

        status_counts[status.value] += 1
        lo_counts[str(lo_id)] += 1

    await db.flush()
    await db.commit()

    return BackgroundSeedSummary(
        total_created=count, by_status=dict(status_counts), by_lo=dict(lo_counts)
    )
