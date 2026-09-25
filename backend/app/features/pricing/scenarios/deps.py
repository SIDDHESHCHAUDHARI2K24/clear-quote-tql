"""Scope-check dependency for pricing routes keyed by `scenario_id` rather
than `application_id` directly (phase-p2 merge, H3: real staff auth replaces
CQ-013's `get_current_lo_stub`).

`application_id`-keyed pricing routes (`post_scenario`, and
`pricing.enrichment`'s override/revert routes) use
`app.core.auth.get_scoped_application` directly instead -- this module only
covers the `scenario_id`-keyed ones (`GET /scenarios/{id}/products`,
`POST /scenarios/{id}/autoquote`, `POST /scenarios/{id}/quotes`), since a
scenario has no owner of its own (spec.md): scope is enforced through the
application it belongs to.
"""

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff, scope_applications
from app.core.db import get_db
from app.core.errors import NotFoundError
from app.features.applications.models import Application
from app.features.pricing.scenarios.models import Scenario


async def ensure_scenario_in_scope(
    scenario_id: uuid.UUID,
    user: CurrentStaff,
    db: AsyncSession = Depends(get_db),
) -> None:
    """404s (never 403 -- Decision #11's style) unless `scenario_id`'s
    application is in `user`'s `scope_applications` scope."""
    stmt = scope_applications(
        select(Application.id)
        .join(Scenario, Scenario.application_id == Application.id)
        .where(Scenario.id == scenario_id),
        user,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise NotFoundError(f"Scenario not found: {scenario_id}")
