"""Principal-agnostic pieces shared by `auth/staff` and `auth/borrower`:
the request-IP helper that feeds both principals' per-IP OTP rate limits,
and the request/response shapes that are identical for both (a challenge id
and a 6-digit code), plus the length caps both schema modules apply to
email/password fields.

Defined once here (rather than in one principal's module and imported by
the other) so a later change — e.g. trusting `X-Forwarded-For` behind a
proxy (CQ-035) — lands in one place instead of two.
"""

from fastapi import Request
from pydantic import BaseModel, Field

# RFC 5321's max mailbox length. Password caps sit well above any real
# password so a client can't force an oversized argon2 hash/verify (CPU
# cost scales with input length) before the login/signup rate limit even
# applies.
MAX_EMAIL_LENGTH = 254
MAX_PASSWORD_LENGTH = 256
# `generate_token(24)` yields 32 url-safe chars; the cap keeps arbitrary
# strings out of the Valkey key built from `challenge_id`.
MAX_CHALLENGE_ID_LENGTH = 64
MAX_OTP_CODE_LENGTH = 6


def client_ip(request: Request) -> str:
    """`request.client.host`, or `"unknown"` when no client/connection info
    is available. Feeds the per-IP rate limits in both `staff/service.py`
    and `borrower/service.py` — a later proxy fix (trusting
    `X-Forwarded-For` behind uvicorn `--proxy-headers`, CQ-035) lands here
    once instead of in two routers."""
    return request.client.host if request.client is not None else "unknown"


class ChallengeResponse(BaseModel):
    challenge_id: str


class OtpVerifyRequest(BaseModel):
    challenge_id: str = Field(max_length=MAX_CHALLENGE_ID_LENGTH)
    code: str = Field(max_length=MAX_OTP_CODE_LENGTH)
