"""Injectable "now" (P5/P6 foundation, phase-p5-p6-plan.md E2).

`now()` returns the current UTC time, unless the `clock_now` setting
(`CLOCK_NOW`, ISO-8601) is set, in which case it returns that instant.
Tests and demos freeze time by setting `CLOCK_NOW` (or monkeypatching
`get_settings`); nothing else changes. New P5/P6 code reads the time
through this function; older code is not refactored.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import get_settings


def parse_instant(value: str) -> datetime:
    """Parses an ISO-8601 instant; a naive value is taken as UTC. Accepts a
    trailing `Z`."""
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def now() -> datetime:
    """The current time as a timezone-aware UTC `datetime`, honouring the
    `clock_now` override. Reads settings on every call, so an override set
    mid-process (tests) takes effect immediately."""
    override = get_settings().clock_now
    if override:
        return parse_instant(override)
    return datetime.now(UTC)
