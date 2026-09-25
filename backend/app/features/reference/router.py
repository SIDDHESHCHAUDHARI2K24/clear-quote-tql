"""`GET /reference/metros?states=FL,NC` (CQ-028 spec, plan.md #17).

Open to any signed-in staff user **or** borrower: the LO's Property tab and
the borrower's apply wizard (CQ-032b) use the same two-tier picker.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AuthenticationError
from app.core.valkey import get_valkey
from app.features.auth.sessions.service import COOKIE_NAMES, get_session_subject
from app.features.reference.schemas import MetrosResponse, StateMetros
from app.features.reference.service import metros_for_states, normalize_states

router = APIRouter(tags=["reference"])


async def require_any_session(
    valkey: Redis = Depends(get_valkey),
    staff_token: str | None = Cookie(default=None, alias=COOKIE_NAMES["staff"]),
    borrower_token: str | None = Cookie(default=None, alias=COOKIE_NAMES["borrower"]),
) -> None:
    if staff_token is not None and await get_session_subject(
        valkey, principal="staff", token=staff_token
    ):
        return
    if borrower_token is not None and await get_session_subject(
        valkey, principal="borrower", token=borrower_token
    ):
        return
    raise AuthenticationError("Not signed in")


@router.get(
    "/reference/metros",
    response_model=MetrosResponse,
    dependencies=[Depends(require_any_session)],
)
async def list_metros(
    states: str = Query(..., description="Comma-separated state codes, e.g. FL,NC"),
    db: AsyncSession = Depends(get_db),
) -> MetrosResponse:
    codes = normalize_states(states.split(","))
    metros = await metros_for_states(db, codes)
    return MetrosResponse(
        states=[StateMetros(state=state, metros=metros[state]) for state in codes]
    )
