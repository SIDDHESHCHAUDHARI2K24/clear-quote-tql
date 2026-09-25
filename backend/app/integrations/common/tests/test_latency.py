"""AC3: latency bounds and the disable switch."""

import asyncio
import time

import pytest

from app.core.config import get_settings
from app.integrations.common.latency import simulate_latency


async def test_latency_disabled_completes_100_calls_under_one_second() -> None:
    """`backend/conftest.py` sets `INTEGRATION_LATENCY_ENABLED=false` for the
    whole session, so this exercises the default (disabled-in-tests) path."""
    assert get_settings().integration_latency_enabled is False

    start = time.monotonic()
    results = await asyncio.gather(*(simulate_latency("rent") for _ in range(100)))
    elapsed = time.monotonic() - start

    assert results == [0] * 100
    assert elapsed < 1.0


async def test_latency_enabled_bounds_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flips latency back on for this one test only (module-level `Settings`
    instance is `@lru_cache`d, so mutating the cached instance is how every
    other call site sees the change too)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "integration_latency_enabled", True)

    results = await asyncio.gather(*(simulate_latency("rent") for _ in range(100)))

    assert len(results) == 100
    assert all(
        settings.integration_latency_min_ms <= ms <= settings.integration_latency_max_ms
        for ms in results
    )
