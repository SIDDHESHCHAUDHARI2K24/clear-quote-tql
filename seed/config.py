"""Seed-only configuration read from the environment.

Kept separate from `app.core.config.Settings` (CQ-004) because these knobs
(`SEED_RNG_SEED`, `SEED_FAST_ADAPTERS`) only ever matter to `seed/reset.py`
and its tests, never to the running API/worker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# AC5: the background generator's determinism contract is pinned to this
# exact literal value.
DEFAULT_SEED_RNG_SEED = 20260101


@dataclass(frozen=True)
class SeedConfig:
    rng_seed: int
    """Seeds `random.Random(rng_seed)` for the background generator (AC5)."""

    fast_adapters: bool
    """When True, `seed/reset.py` sets `INTEGRATION_LATENCY_ENABLED=false`
    before the app's `Settings` is ever constructed (plan.md decision #5 --
    CQ-009's mocks add 200-1,200ms per call; the 60s reset budget can't
    absorb that across ~10 personas' worth of adapter calls)."""


def load_seed_config() -> SeedConfig:
    rng_seed = int(os.environ.get("SEED_RNG_SEED", DEFAULT_SEED_RNG_SEED))
    fast_adapters = os.environ.get("SEED_FAST_ADAPTERS", "1") != "0"
    return SeedConfig(rng_seed=rng_seed, fast_adapters=fast_adapters)
