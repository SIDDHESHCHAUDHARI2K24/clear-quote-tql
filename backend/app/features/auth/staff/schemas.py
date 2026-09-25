"""Pydantic request/response schemas for `/api/v1/auth/staff/*`.

`StaffLoginRequest.email` is a plain `str` rather than pydantic's `EmailStr`
(plan.md T3): `EmailStr` requires the `email-validator` package, which isn't
a project dependency and this item doesn't add it — `staff/service.py`
normalizes with `.strip().lower()` before use.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import UserRole

# RFC 5321's max mailbox length. `password` is capped well above any real
# password so a client can't force an oversized argon2 hash/verify (CPU
# cost scales with input length) before the login rate limit even applies.
_MAX_EMAIL_LENGTH = 254
_MAX_PASSWORD_LENGTH = 256
# `generate_token(24)` yields 32 url-safe chars; the cap keeps arbitrary
# strings out of the Valkey key built from `challenge_id`.
_MAX_CHALLENGE_ID_LENGTH = 64


class StaffLoginRequest(BaseModel):
    email: str = Field(max_length=_MAX_EMAIL_LENGTH)
    password: str = Field(max_length=_MAX_PASSWORD_LENGTH)


class ChallengeResponse(BaseModel):
    challenge_id: str


class OtpVerifyRequest(BaseModel):
    challenge_id: str = Field(max_length=_MAX_CHALLENGE_ID_LENGTH)
    code: str = Field(max_length=6)


class StaffUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    nmls: str | None
    title: str | None
    phone: str | None
