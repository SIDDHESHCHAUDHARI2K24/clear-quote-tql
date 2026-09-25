"""Pydantic request/response schemas for `/api/v1/auth/borrower/*`.

`ChallengeResponse` and `OtpVerifyRequest` are reused as-is from
`auth.staff.schemas` (both are already principal-agnostic — a challenge id
and a 6-digit code) rather than duplicated here; the router imports them
directly. Everything borrower-specific — sign-up, login, and the `/me`
shape (plan.md Decision #10) — is defined in this module.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Same caps as `auth.staff.schemas` (plan.md T1 build note #3): RFC 5321's
# max mailbox length for email, and a password cap well above any real
# password so a client can't force an oversized argon2 hash/verify before
# the login/signup rate limit even applies.
_MAX_EMAIL_LENGTH = 254
_MAX_PASSWORD_LENGTH = 256
_MAX_FULL_NAME_LENGTH = 200


class BorrowerSignupRequest(BaseModel):
    full_name: str
    email: str = Field(max_length=_MAX_EMAIL_LENGTH)
    password: str = Field(max_length=_MAX_PASSWORD_LENGTH)

    @field_validator("full_name")
    @classmethod
    def _strip_and_bound_full_name(cls, value: str) -> str:
        """Strips first, then bounds to 1-200 chars (spec: "1-200 after
        strip") — a `Field(max_length=...)` constraint would instead cap
        the raw, unstripped input."""
        stripped = value.strip()
        if not (1 <= len(stripped) <= _MAX_FULL_NAME_LENGTH):
            raise ValueError(
                f"full_name must be 1-{_MAX_FULL_NAME_LENGTH} characters after stripping"
            )
        return stripped


class BorrowerLoginRequest(BaseModel):
    email: str = Field(max_length=_MAX_EMAIL_LENGTH)
    password: str = Field(max_length=_MAX_PASSWORD_LENGTH)


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
