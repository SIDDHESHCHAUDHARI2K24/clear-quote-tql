"""CQ-030 stale job result. A plain dataclass (not Pydantic) so Temporal's
default data converter can carry it as `mark_stale_activity`'s return
value; the admin endpoint maps it onto its own response model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StaleResult:
    """What one `mark_stale` run changed. Every count is zero on a second
    run at the same `now` (spec.md step 4, AC2)."""

    quotes_marked_stale: int = 0
    """`quotes` rows whose `stale` flag went false -> true this run."""
    versions_expired: int = 0
    """Sent `quote_package_versions` stamped with `expired_at` this run."""
    applications_marked_stale: int = 0
    """Applications moved Priced/Sent/Viewed -> Stale (one activity event
    each)."""
    application_ids: list[str] = field(default_factory=list)
    """Ids (as strings) of the applications moved to Stale this run."""
