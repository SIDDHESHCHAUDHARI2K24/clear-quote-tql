"""Borrower auth routes: `/api/v1/auth/borrower/{signup, login, otp/verify,
logout, me}`."""

from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentBorrower
from app.core.db import get_db
from app.core.valkey import get_valkey
from app.features.auth.borrower import service
from app.features.auth.borrower.schemas import (
    BorrowerLoginRequest,
    BorrowerMeOut,
    BorrowerSignupRequest,
)
from app.features.auth.sessions.service import (
    COOKIE_NAMES,
    clear_session_cookie,
    create_session,
    delete_session,
    set_session_cookie,
)
from app.features.auth.staff.schemas import ChallengeResponse, OtpVerifyRequest

router = APIRouter(prefix="/auth/borrower", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


@router.post("/signup", response_model=ChallengeResponse)
async def signup(
    body: BorrowerSignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> ChallengeResponse:
    challenge_id = await service.signup(
        db,
        valkey,
        full_name=body.full_name,
        email=body.email,
        password=body.password,
        ip=_client_ip(request),
    )
    return ChallengeResponse(challenge_id=challenge_id)


@router.post("/login", response_model=ChallengeResponse)
async def login(
    body: BorrowerLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> ChallengeResponse:
    challenge_id = await service.login(
        db, valkey, email=body.email, password=body.password, ip=_client_ip(request)
    )
    return ChallengeResponse(challenge_id=challenge_id)


@router.post("/otp/verify", response_model=BorrowerMeOut)
async def verify_otp(
    body: OtpVerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> BorrowerMeOut:
    account = await service.verify_otp(db, valkey, challenge_id=body.challenge_id, code=body.code)
    token = await create_session(valkey, principal="borrower", subject_id=str(account.id))
    set_session_cookie(response, "borrower", token)
    return await service.build_me(db, account)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    valkey: Redis = Depends(get_valkey),
) -> None:
    token = request.cookies.get(COOKIE_NAMES["borrower"])
    if token is not None:
        await delete_session(valkey, principal="borrower", token=token)
    clear_session_cookie(response, "borrower")


@router.get("/me", response_model=BorrowerMeOut)
async def get_me(account: CurrentBorrower, db: AsyncSession = Depends(get_db)) -> BorrowerMeOut:
    return await service.build_me(db, account)
