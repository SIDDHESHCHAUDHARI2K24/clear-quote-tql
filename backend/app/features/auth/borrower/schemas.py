"""Pydantic request/response schemas for `/api/v1/auth/borrower/*`.

`ChallengeResponse` and `OtpVerifyRequest` live in `auth.common` (both are
principal-agnostic — a challenge id and a 6-digit code); the router imports
them from there directly rather than from `auth.staff.schemas`. Everything
borrower-specific — sign-up, login, and the `/me` shape (plan.md Decision
#10) — is defined in this module.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.auth.common import MAX_EMAIL_LENGTH, MAX_PASSWORD_LENGTH
from app.features.auth.users.service import MIN_PASSWORD_LENGTH

_MAX_FULL_NAME_LENGTH = 200
# A raw cap well above `_MAX_FULL_NAME_LENGTH` so a multi-megabyte
# `full_name` is rejected by pydantic's own `Field` constraint before ever
# reaching `_strip_and_bound_full_name` below — a bare `field_validator`
# with no `Field(max_length=...)` still runs `.strip()` on however large a
# string the caller sends.
_MAX_FULL_NAME_RAW_LENGTH = 256


class BorrowerSignupRequest(BaseModel):
    full_name: str = Field(max_length=_MAX_FULL_NAME_RAW_LENGTH)
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    # `min_length` puts the password rule in the OpenAPI contract (plan.md
    # fix 3), so a too-short password gets pydantic's 422 before
    # `borrower/service.py::signup` ever runs — that service-level check
    # stays as defense in depth for any non-HTTP caller.
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("full_name")
    @classmethod
    def _strip_and_bound_full_name(cls, value: str) -> str:
        """Strips first, then bounds to 1-200 chars (spec: "1-200 after
        strip") — a `Field(max_length=...)` constraint would instead cap
        the raw, unstripped input. The raw `Field(max_length=...)` above
        still bounds the unstripped input, just at a higher ceiling, so a
        huge string never reaches this validator."""
        stripped = value.strip()
        if not (1 <= len(stripped) <= _MAX_FULL_NAME_LENGTH):
            raise ValueError(
                f"full_name must be 1-{_MAX_FULL_NAME_LENGTH} characters after stripping"
            )
        return stripped


class BorrowerLoginRequest(BaseModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class LatestApplicationOut(BaseModel):
    id: uuid.UUID
    status: str


class BorrowerMeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    email: str
    client_id: uuid.UUID
    full_name: str
    first_name: str
    latest_application: LatestApplicationOut | None
