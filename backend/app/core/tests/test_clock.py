"""`core/clock.now()` (P5/P6 foundation, E2): real UTC time by default,
the `CLOCK_NOW` override when set."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core import clock
from app.core.config import get_settings


def _override(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    settings = get_settings().model_copy(update={"clock_now": value})
    monkeypatch.setattr(clock, "get_settings", lambda: settings)


def test_now_defaults_to_real_utc_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _override(monkeypatch, None)
    before = datetime.now(UTC)
    result = clock.now()
    after = datetime.now(UTC)
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)
    assert before <= result <= after


def test_now_honours_clock_now_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _override(monkeypatch, "2026-10-17T12:30:00+00:00")
    assert clock.now() == datetime(2026, 10, 17, 12, 30, tzinfo=UTC)


def test_override_accepts_z_suffix_and_converts_offsets_to_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _override(monkeypatch, "2026-10-17T12:30:00Z")
    assert clock.now() == datetime(2026, 10, 17, 12, 30, tzinfo=UTC)

    _override(monkeypatch, "2026-10-17T08:30:00-04:00")
    result = clock.now()
    assert result == datetime(2026, 10, 17, 12, 30, tzinfo=UTC)
    assert result.utcoffset() == timedelta(0)


def test_naive_override_is_taken_as_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    _override(monkeypatch, "2026-10-17T12:30:00")
    assert clock.now() == datetime(2026, 10, 17, 12, 30, tzinfo=UTC)


def test_clock_now_env_var_reaches_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOCK_NOW", "2026-01-02T03:04:05Z")
    get_settings.cache_clear()
    try:
        assert clock.now() == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    finally:
        monkeypatch.delenv("CLOCK_NOW")
        get_settings.cache_clear()
