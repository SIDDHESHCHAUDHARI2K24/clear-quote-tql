"""Pydantic request/response schemas for `/api/v1/auth/staff/*`.

`StaffLoginRequest.email` is a plain `str` rather than pydantic's `EmailStr`
(plan.md T3): `EmailStr` requires the `email-validator` package, which isn't
a project dependency and this item doesn't add it — `staff/service.py`
normalizes with `.strip().lower()` before use.

`ChallengeResponse` and `OtpVerifyRequest` live in `auth.common` (shared
with `auth.borrower`); `staff/router.py` imports them from there directly.
`StaffLoginRequest.password` deliberately has no `min_length`: unlike
sign-up, login must not reveal the password rule to a caller who doesn't
already know a valid password.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import UserRole
from app.features.auth.common import MAX_EMAIL_LENGTH, MAX_PASSWORD_LENGTH


class StaffLoginRequest(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class StaffUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    nmls: str | None
    title: str | None
    phone: str | None
