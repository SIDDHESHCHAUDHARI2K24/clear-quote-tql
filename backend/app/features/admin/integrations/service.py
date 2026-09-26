"""`GET/PUT /admin/integrations` (spec.md "Integration panel", Admin only).

Reads `integration_calls` (CQ-009's `record_call`, `integrations/common/
models.py`) for the last-call/latency/result/hourly-count columns, and
`integrations/common/failure_toggle.py` (`is_forced_to_fail`/
`set_forced_failure`, Valkey-backed) for the toggle -- reused as-is, no
adaptation needed (spec.md's "if CQ-009 exposes it differently, adapt and
log a Decision" does not apply here).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now as clock_now
from app.core.errors import NotFoundError
from app.features.admin.integrations.schemas import AdapterStatus
from app.integrations.common.failure_toggle import is_forced_to_fail, set_forced_failure
from app.integrations.common.models import IntegrationCall

# Order matches the CQ-029 prompt's adapter list and system-design.md's
# "Emulated integrations" table (`LosClient (Encompass)`, etc.); `credit`,
# `property_search` and `crm` have no named real-world vendor in that
# table, so their `provider` is a short description instead.
ADAPTER_PROVIDERS: dict[str, str] = {
    "credit": "Experian (credit bureau)",
    "crm": "Internal CRM log",
    "insurance": "Steadily",
    "los": "Encompass",
    "pricing": "Optimal Blue",
    "property_search": "MLS / IDX property search",
    "rent": "RentCast",
    "str": "AirDNA",
    "tax": "SmartAsset / county records",
}


def _last_result(last_call: IntegrationCall | None) -> str:
    if last_call is None:
        return "never_called"
    if last_call.success:
        return "ok"
    return last_call.error_code or "error"


async def _adapter_status(db: AsyncSession, adapter: str, provider: str) -> AdapterStatus:
    now = clock_now()
    hour_ago = now - timedelta(hours=1)

    last_call = (
        (
            await db.execute(
                select(IntegrationCall)
                .where(IntegrationCall.adapter == adapter)
                .order_by(IntegrationCall.called_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    calls_last_hour = (
        await db.execute(
            select(func.count())
            .select_from(IntegrationCall)
            .where(IntegrationCall.adapter == adapter, IntegrationCall.called_at >= hour_ago)
        )
    ).scalar_one()

    return AdapterStatus(
        adapter=adapter,
        provider=provider,
        last_call_at=last_call.called_at if last_call else None,
        last_latency_ms=last_call.latency_ms if last_call else None,
        last_result=_last_result(last_call),
        calls_last_hour=calls_last_hour,
        force_failure=await is_forced_to_fail(adapter),
    )


async def list_integration_status(db: AsyncSession) -> list[AdapterStatus]:
    """Same shape as `_adapter_status`, batched across all 9 adapters
    (code review finding: the naive per-adapter version made ~27 sequential
    round trips -- 2 DB queries + 1 Valkey GET each -- for one page load).

    The two DB queries run one after another (still 2 round trips, not 18):
    an `AsyncSession` only has one underlying connection, so they can't run
    concurrently the way the Valkey lookups below safely can (`redis.
    asyncio.Redis` pools its own connections). `DISTINCT ON` requires
    Postgres; this module and `IntegrationCall` are Postgres-only already
    (CQ-004/009), so that's not a new constraint.
    """
    now = clock_now()
    hour_ago = now - timedelta(hours=1)

    latest_stmt = (
        select(IntegrationCall)
        .ext(distinct_on(IntegrationCall.adapter))
        .order_by(IntegrationCall.adapter, IntegrationCall.called_at.desc())
    )
    latest_by_adapter = {
        call.adapter: call for call in (await db.execute(latest_stmt)).scalars().all()
    }

    counts_stmt = (
        select(IntegrationCall.adapter, func.count())
        .where(IntegrationCall.called_at >= hour_ago)
        .group_by(IntegrationCall.adapter)
    )
    counts_by_adapter: dict[str, int] = dict((await db.execute(counts_stmt)).all())  # type: ignore[arg-type]

    force_failures = await asyncio.gather(
        *(is_forced_to_fail(adapter) for adapter in ADAPTER_PROVIDERS)
    )

    results = []
    for (adapter, provider), force_failure in zip(
        ADAPTER_PROVIDERS.items(), force_failures, strict=True
    ):
        last_call = latest_by_adapter.get(adapter)
        results.append(
            AdapterStatus(
                adapter=adapter,
                provider=provider,
                last_call_at=last_call.called_at if last_call else None,
                last_latency_ms=last_call.latency_ms if last_call else None,
                last_result=_last_result(last_call),
                calls_last_hour=counts_by_adapter.get(adapter, 0),
                force_failure=force_failure,
            )
        )
    return results


async def get_adapter_status(db: AsyncSession, adapter: str) -> AdapterStatus:
    if adapter not in ADAPTER_PROVIDERS:
        raise NotFoundError(f"Unknown adapter: {adapter}")
    return await _adapter_status(db, adapter, ADAPTER_PROVIDERS[adapter])


async def set_adapter_force_failure(
    db: AsyncSession, adapter: str, force_failure: bool
) -> AdapterStatus:
    if adapter not in ADAPTER_PROVIDERS:
        raise NotFoundError(f"Unknown adapter: {adapter}")
    await set_forced_failure(adapter, force_failure)
    return await get_adapter_status(db, adapter)
