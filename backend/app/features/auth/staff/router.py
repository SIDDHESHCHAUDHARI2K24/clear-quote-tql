"""Staff auth routes: `/api/v1/auth/staff/{login, otp/verify, logout, me}`."""

from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentStaff
from app.core.db import get_db
from app.core.valkey import get_valkey
from app.features.auth.models import User
from app.features.auth.sessions.service import (
    COOKIE_NAMES,
    clear_session_cookie,
    create_session,
    delete_session,
    set_session_cookie,
)
from app.features.auth.staff import service
from app.features.auth.staff.schemas import (
    ChallengeResponse,
    OtpVerifyRequest,
    StaffLoginRequest,
    StaffUserOut,
)

router = APIRouter(prefix="/auth/staff", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


@router.post("/login", response_model=ChallengeResponse)
async def login(
    body: StaffLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> ChallengeResponse:
    challenge_id = await service.login(
        db, valkey, email=body.email, password=body.password, ip=_client_ip(request)
    )
    return ChallengeResponse(challenge_id=challenge_id)


@router.post("/otp/verify", response_model=StaffUserOut)
async def verify_otp(
    body: OtpVerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> User:
    user = await service.verify_otp(db, valkey, challenge_id=body.challenge_id, code=body.code)
    token = await create_session(valkey, principal="staff", subject_id=str(user.id))
    set_session_cookie(response, "staff", token)
    return user


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    valkey: Redis = Depends(get_valkey),
) -> None:
    token = request.cookies.get(COOKIE_NAMES["staff"])
    if token is not None:
        await delete_session(valkey, principal="staff", token=token)
    clear_session_cookie(response, "staff")


@router.get("/me", response_model=StaffUserOut)
async def get_me(user: CurrentStaff) -> User:
    return user
