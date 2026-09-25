"""`POST /api/v1/portal/support` request/response shapes (CQ-034 spec.md).

AC3: a 9-character message, or `preferred_contact=phone` with no phone, are
both rejected with pydantic field errors (a 422 via `Field`/`field_validator`/
`model_validator`), not a hand-rolled `ValidationAppError` -- same shape as
`auth/borrower/schemas.py`'s `full_name` validator, which every existing
frontend error-extraction helper (`@cq/ui`'s `extractErrorMessage`) already
parses.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MESSAGE_MIN_LENGTH = 10
_MESSAGE_MAX_LENGTH = 2000
# A raw cap above `_MESSAGE_MAX_LENGTH` so a multi-megabyte message is
# rejected by pydantic's own `Field` constraint before the strip/bounds
# validator below ever runs on it (mirrors `auth/borrower/schemas.py`'s
# `_MAX_FULL_NAME_RAW_LENGTH` reasoning).
_MESSAGE_MAX_RAW_LENGTH = 4000
_PHONE_MAX_LENGTH = 32


class SupportTopic(StrEnum):
    APPLICATION = "application"
    QUOTE = "quote"
    DOCUMENTS = "documents"
    OTHER = "other"


class PreferredContact(StrEnum):
    EMAIL = "email"
    PHONE = "phone"


class SupportRequestCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic: SupportTopic
    message: str = Field(max_length=_MESSAGE_MAX_RAW_LENGTH)
    preferred_contact: PreferredContact
    phone: str | None = Field(default=None, max_length=_PHONE_MAX_LENGTH)

    @field_validator("message")
    @classmethod
    def _strip_and_bound_message(cls, value: str) -> str:
        stripped = value.strip()
        if not (_MESSAGE_MIN_LENGTH <= len(stripped) <= _MESSAGE_MAX_LENGTH):
            raise ValueError(
                f"message must be {_MESSAGE_MIN_LENGTH}-{_MESSAGE_MAX_LENGTH} "
                "characters after stripping"
            )
        return stripped

    @field_validator("phone")
    @classmethod
    def _strip_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _phone_required_for_phone_contact(self) -> SupportRequestCreate:
        if self.preferred_contact is PreferredContact.PHONE and not self.phone:
            raise ValueError("phone is required when preferred_contact is phone")
        return self


class SupportLoContact(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    email: str
    phone: str | None


class SupportRequestResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    reference: str
    lo: SupportLoContact
