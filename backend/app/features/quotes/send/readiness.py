"""Send readiness (CQ-019 spec: `GET /packages/{id}/readiness`).

Blockers, in the order the Send button's tooltip picks the first one
(plan.md Decision 12):

1. `quotes_stale` -- a selected quote is stale: `quote.stale`, or priced more
   than 21 days ago (catalog §12 `is_rate_stale`; plan.md Decision 9).
2. `quote_not_offered` -- a selected Manual quote whose product left the
   grid on the last reprice (CQ-018 follow-up; plan.md Decision 11).
3. `open_flag` -- one per open flag with `blocking` severity (the spec's
   "error"; plan.md Decision 10), naming the field and rule.
4. `no_quotes` / `no_recommended_quote`.
5. `borrower_email_missing`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApplicationTab, FlagSeverity
from app.features.applications.verification.models import Flag
from app.features.quotes.builder.models import Quote
from app.features.quotes.send.models import QuotePackage
from app.features.quotes.send.view_model import load_package_context

RATE_STALE_DAYS = 21
"""catalog §12 `is_rate_stale`: "True if quote age > 21 days"."""

STALE_MESSAGE = "Quotes are out of date"

_FIELD_LABELS = {
    "occupancy_type": "Occupancy type",
    "current_residence_years": "Housing history",
    "representative_fico": "Credit score",
    "borrower_ssn": "SSN",
    "borrower_dob": "Date of birth",
}
_RULE_TEXT = {
    "ob_required_field": "required for pricing",
    "housing_history_24mo": "under 24 months of history",
    "ssn_format": "invalid format",
    "dob_format": "invalid format",
    "assets_vs_ctc_reserves": "assets don't cover cash to close and reserves",
    "dti_primary": "DTI above the limit",
}


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str
    tab: str


def flag_message(field_key: str, rule: str) -> str:
    field = _FIELD_LABELS.get(field_key, field_key.replace("_", " ").capitalize())
    reason = _RULE_TEXT.get(rule, rule.replace("_", " "))
    return f"Open flag: {field} — {reason}"


def is_rate_stale(quote: Quote, now: datetime) -> bool:
    return quote.stale or quote.priced_at < now - timedelta(days=RATE_STALE_DAYS)


async def _not_offered(db: AsyncSession, quotes: list[Quote]) -> int:
    """Manual quotes kept stale by a reprice that re-priced their
    scenario's Par after them: the product is no longer on the grid."""
    manual = [q for q in quotes if q.stale and q.label not in ("Par", "Buydown")]
    if not manual:
        return 0
    pars = {
        q.scenario_id: q.priced_at
        for q in (
            await db.execute(
                select(Quote).where(
                    Quote.scenario_id.in_({q.scenario_id for q in manual}), Quote.label == "Par"
                )
            )
        ).scalars()
    }
    return sum(1 for q in manual if q.scenario_id in pars and pars[q.scenario_id] > q.priced_at)


async def package_blockers(
    db: AsyncSession, package: QuotePackage, *, now: datetime | None = None
) -> list[Blocker]:
    now = now or datetime.now(UTC)
    ctx = await load_package_context(db, package)
    blockers: list[Blocker] = []

    if any(is_rate_stale(q, now) for q in ctx.quotes):
        blockers.append(Blocker("quotes_stale", STALE_MESSAGE, ApplicationTab.PRICING.value))
    not_offered = await _not_offered(db, ctx.quotes)
    if not_offered:
        noun = "manual quote is" if not_offered == 1 else "manual quotes are"
        blockers.append(
            Blocker(
                "quote_not_offered",
                f"{not_offered} {noun} no longer offered — delete or re-pick",
                ApplicationTab.PRICING.value,
            )
        )

    flags = (
        await db.execute(
            select(Flag)
            .where(
                Flag.application_id == ctx.application.id,
                Flag.resolved_at.is_(None),
                Flag.severity == FlagSeverity.BLOCKING,
            )
            .order_by(Flag.created_at, Flag.id)
        )
    ).scalars()
    blockers.extend(
        Blocker("open_flag", flag_message(f.field_key, f.rule), f.tab.value) for f in flags
    )

    if not ctx.quotes:
        blockers.append(
            Blocker("no_quotes", "Select at least one quote", ApplicationTab.SEND.value)
        )
    elif package.recommended_quote_id not in {q.id for q in ctx.quotes}:
        blockers.append(
            Blocker("no_recommended_quote", "Pick a recommended quote", ApplicationTab.SEND.value)
        )

    if not (ctx.client.email or "").strip():
        blockers.append(
            Blocker(
                "borrower_email_missing",
                "Borrower email is missing",
                ApplicationTab.BORROWERS.value,
            )
        )
    return blockers
