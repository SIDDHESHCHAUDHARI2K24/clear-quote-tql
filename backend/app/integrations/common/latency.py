"""Shared latency simulation every mock adapter awaits first.

`INTEGRATION_LATENCY_ENABLED=false` (set for the whole pytest session by
`backend/conftest.py`) disables sleeping entirely so the suite stays fast;
`app.integrations.common.tests.test_latency` flips it back on for its one
timing-sensitive test.
"""

import asyncio
import random

from app.core.config import get_settings


async def simulate_latency(adapter: str) -> int:
    """Sleeps a random duration between the configured bounds and returns it.

    `adapter` is unused by the simulation itself (every adapter shares one
    latency distribution) but kept in the signature per spec.md so call
    sites read the same way as `is_forced_to_fail`/`record_call`.
    """
    settings = get_settings()
    if not settings.integration_latency_enabled:
        return 0
    duration_ms = random.uniform(
        settings.integration_latency_min_ms, settings.integration_latency_max_ms
    )
    await asyncio.sleep(duration_ms / 1000)
    return round(duration_ms)
