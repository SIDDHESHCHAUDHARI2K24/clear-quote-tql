"""`GET /applications/{id}/activity` (spec.md "Timeline").

`list_activity` is the single-application entry point: paginates
`activity_events` newest first (plan.md decision — `at DESC, id DESC` for a
stable order when two events share a timestamp), then maps each row to an
`ActivityEventOut` via `_resolve_actor` (plan.md decision 3) and
`describe_event` (decision 4).

`list_activity_for_applications` is the multi-application entry point CQ-026
(clients wave) uses for its client-detail page's merged "Activity" section
(review round 1: batched into one query + one staff-name lookup across every
application, rather than the caller running `list_activity` once per
application).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, paginate
from app.features.applications.models import Application
from app.features.applications.timeline.models import ActivityEvent
from app.features.applications.timeline.schemas import ActivityActor, ActivityEventOut
from app.features.auth.models import User
from app.features.clients.models import Client

_ACTOR_SYSTEM = "system"

# Written with actor="system" today (portal/actions, portal/reports
# services) but conceptually the borrower's own action — shown as the
# borrower, not quieted as automation (plan.md decision 3).
_BORROWER_EVENT_TYPES = {
    "quote.viewed",
    "quote.move_forward",
    "quote.ask_other",
    "quote.ask_updated",
    "quote.option_selected",
    "application.submitted",
    "support.requested",
}

_ACTOR_BORROWER = "borrower"


def _payload_summary(payload: Any) -> str | None:
    if not payload:
        return None
    if isinstance(payload, dict):
        # Sorted by key, not "first 5 as read back" -- a JSONB column
        # doesn't preserve insertion order (Postgres normalizes key order
        # by length then bytes), so slicing the dict as returned would
        # show an arbitrary subset rather than a deterministic one (code
        # review finding).
        parts = [f"{key}={value}" for key, value in sorted(payload.items())[:5]]
        return ", ".join(parts) if parts else None
    return str(payload)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def describe_event(event_type: str, payload: Any) -> str:  # noqa: PLR0911
    """Pure mapping `type` + `payload` -> a human sentence (plan.md decision
    4). Unknown types fall back to a humanized version of the type string,
    so a future event type (CQ-030 stale marking, CQ-033 consent, CQ-020/24
    real sends) never breaks the timeline -- it just reads generically
    until this function is extended.
    """
    data = payload if isinstance(payload, dict) else {}

    if event_type == "pipeline.imported":
        parties = data.get("parties_created")
        if isinstance(parties, int):
            return f"Imported from the LOS ({_plural(parties, 'borrower')} on file)"
        return "Imported from the LOS"
    if event_type == "pipeline.verified":
        rule_count = data.get("rule_count")
        if isinstance(rule_count, int):
            return f"Passed verification ({_plural(rule_count, 'rule')} checked)"
        return "Passed verification"
    if event_type == "pipeline.flagged":
        # `failed_rules` (Temporal activity) or `flags` (seed's
        # `_add_activity_event` shorthand, see seed/loader.py) — same
        # meaning, different key.
        failed_rules = data.get("failed_rules") or data.get("flags")
        if isinstance(failed_rules, list) and failed_rules:
            rule_list = ", ".join(str(r) for r in failed_rules)
            return f"Verification flagged {_plural(len(failed_rules), 'issue')}: {rule_list}"
        return "Verification flagged an issue"
    if event_type == "pipeline.enriched":
        if "field_keys_written" in data:
            written = data.get("field_keys_written") or []
            return f"Enriched pricing inputs ({_plural(len(written), 'field')} filled in)"
        if "validated" in data:
            return "Validated pricing inputs are complete"
        if "scenario_ids" in data:
            scenario_ids = data.get("scenario_ids") or []
            return f"Priced {_plural(len(scenario_ids), 'scenario')} from Optimal Blue"
        return "Enriched pricing inputs"
    if event_type == "pipeline.pricing_blocked":
        # `message` (Temporal activity) or `reason` (seed shorthand).
        message = data.get("message") or data.get("reason")
        return f"Pricing blocked: {message}" if message else "Pricing blocked"
    if event_type == "pipeline.priced":
        quote_ids = data.get("quote_ids")
        if isinstance(quote_ids, list):
            return f"Drafted {_plural(len(quote_ids), 'quote')}"
        return "Drafted the quote set"
    if event_type == "pipeline.resumed":
        return "Pipeline resumed after the flag was resolved"
    if event_type == "quote.viewed":
        version = data.get("version")
        return f"Viewed the quote package (v{version})" if version else "Viewed the quote package"
    if event_type == "quote.move_forward":
        return "Asked to move forward with the selected quote"
    if event_type == "quote.ask_other":
        return "Asked a question about other options"
    if event_type == "quote.ask_updated":
        return "Asked for updated numbers (the report had expired)"
    if event_type == "quote.sent":
        return "Sent the quote package to the borrower"
    if event_type == "quote.option_selected":
        return "Selected a quote option"
    if event_type == "application.withdrawn":
        reason = data.get("reason")
        return f"Application withdrawn: {reason}" if reason else "Application withdrawn"
    if event_type == "application.closed":
        reason = data.get("reason")
        return f"Application closed: {reason}" if reason else "Application closed"
    if event_type == "application.submitted":
        return "Submitted the application"
    if event_type == "application.assigned":
        lo_name = data.get("lo_name")
        return f"Assigned to {lo_name}" if lo_name else "Assigned to a loan officer"
    if event_type == "support.requested":
        topic = data.get("topic")
        return f"Requested support: {topic}" if topic else "Requested support"

    # Event types written outside this service (CQ-028a's
    # applications/sections/events.py, CQ-030's stale events, and any
    # future writer) carry their own human-readable `message` in the
    # payload -- prefer it over the generic humanized fallback below (M2).
    message = data.get("message")
    if isinstance(message, str) and message:
        return message

    return event_type.replace(".", " ").replace("_", " ").capitalize()


def _staff_actor_id(event: ActivityEvent) -> uuid.UUID | None:
    """The staff `User.id` an event's `actor` names, or `None` when the
    actor is the borrower, the system, or not a real user id."""
    if event.type in _BORROWER_EVENT_TYPES or event.actor in (_ACTOR_SYSTEM, _ACTOR_BORROWER):
        return None
    try:
        return uuid.UUID(event.actor)
    except ValueError:
        return None


def _resolve_actor(
    event: ActivityEvent,
    *,
    borrower_name: str,
    staff_names: dict[uuid.UUID, str],
) -> ActivityActor:
    if event.type in _BORROWER_EVENT_TYPES or event.actor == _ACTOR_BORROWER:
        return ActivityActor(kind="borrower", name=borrower_name)
    # No separate `actor == _ACTOR_SYSTEM` branch (code review round 2):
    # `_staff_actor_id` already returns `None` for the system actor (and
    # for anything else that isn't a real user id), and `None` already
    # means "system" below -- a second, differently-worded check for the
    # same sentinel was dead weight two ways to say the same thing could
    # drift apart.
    user_id = _staff_actor_id(event)
    if user_id is None:
        return ActivityActor(kind="system", name="System")
    return ActivityActor(kind="staff", name=staff_names.get(user_id, "Unknown user"))


async def _events_to_out(
    db: AsyncSession, events: list[ActivityEvent], *, borrower_name: str
) -> list[ActivityEventOut]:
    """Batched `ActivityEvent` -> `ActivityEventOut` mapping shared by
    `list_activity` and `list_activity_for_applications`: one lookup for
    every staff actor across `events` instead of a per-row `db.get`
    (code review finding, minor 1)."""
    staff_ids = {uid for event in events if (uid := _staff_actor_id(event)) is not None}
    staff_names: dict[uuid.UUID, str] = {}
    if staff_ids:
        rows = await db.execute(select(User.id, User.full_name).where(User.id.in_(staff_ids)))
        staff_names = dict(rows.all())

    items: list[ActivityEventOut] = []
    for event in events:
        actor = _resolve_actor(event, borrower_name=borrower_name, staff_names=staff_names)
        items.append(
            ActivityEventOut(
                id=event.id,
                actor=actor,
                type=event.type,
                message=describe_event(event.type, event.payload),
                payload_summary=_payload_summary(event.payload),
                at=event.at,
            )
        )
    return items


async def list_activity(
    db: AsyncSession,
    application: Application,
    page: int | None,
    page_size: int | None,
) -> Page[ActivityEventOut]:
    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.application_id == application.id)
        .order_by(ActivityEvent.at.desc(), ActivityEvent.id.desc())
    )
    result = await paginate(db, stmt, page, page_size)

    client = await db.get(Client, application.client_id)
    borrower_name = client.full_name if client is not None else "Borrower"

    items = await _events_to_out(db, result.items, borrower_name=borrower_name)

    return Page[ActivityEventOut](
        items=items, total=result.total, page=result.page, page_size=result.page_size
    )


async def list_activity_for_applications(
    db: AsyncSession, applications: list[Application], *, limit: int = 50
) -> list[ActivityEventOut]:
    """Merged, newest-first activity across several applications that all
    belong to the same client -- CQ-026's client-detail "Activity" section
    (module docstring). One query for the events (capped at `limit`,
    ordered the same as `list_activity`'s own `ORDER BY`) and one batched
    staff-name lookup, instead of the caller running `list_activity` once
    per application -- each of which re-fetched the client row and only
    trimmed to `limit` locally after over-fetching per application (review
    round 1, minor: batched).

    All `applications` are assumed to share one client (CQ-026 is the only
    caller today); `applications[0]`'s client supplies the borrower name.
    """
    if not applications:
        return []
    application_ids = [a.id for a in applications]
    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.application_id.in_(application_ids))
        .order_by(ActivityEvent.at.desc(), ActivityEvent.id.desc())
        .limit(limit)
    )
    events = list((await db.execute(stmt)).scalars().all())
    if not events:
        return []

    client = await db.get(Client, applications[0].client_id)
    borrower_name = client.full_name if client is not None else "Borrower"

    return await _events_to_out(db, events, borrower_name=borrower_name)
