"""Password hashing, OTP codes and opaque tokens shared by CQ-014 (staff)
and CQ-015 (borrower) auth.

Nothing here is principal-specific — `features/auth/otp` and
`features/auth/sessions` build on these primitives for both staff and
borrower flows.
"""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()

# A real argon2 hash of a value nobody can log in with. `verify_password`
# against this always returns False, but takes the same time as a real
# verify — used so an unknown-email login doesn't respond faster than a
# known-email/wrong-password one (Decision #4).
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(plain: str) -> str:
    """Hashes `plain` with argon2 (library defaults)."""
    return _hasher.hash(plain)


def verify_password(hash_: str, plain: str) -> bool:
    """True iff `plain` matches `hash_`. False (never raises) on mismatch
    or on a malformed/foreign hash string.

    `VerificationError` (argon2-cffi's base for both a wrong password —
    its `VerifyMismatchError` subclass — and an argon2-shaped hash that
    fails to decode, e.g. truncated/corrupted) and `InvalidHashError` (a
    string that isn't argon2-shaped at all) are both "not a match", not a
    bug, so both fold into `False` rather than propagating.
    """
    try:
        return _hasher.verify(hash_, plain)
    except (VerificationError, InvalidHashError):
        return False


def generate_otp_code() -> str:
    """A 6-digit, zero-padded OTP code, e.g. `"004821"`."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_token(value: str) -> str:
    """SHA-256 hex digest — used to store OTP codes and session/challenge
    ids at rest (Valkey keys/values) without the plaintext token sitting in
    the store."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def keyed_hash(value: str) -> str:
    """HMAC-SHA256 hex digest keyed with `SECRET_KEY` — used for OTP codes,
    whose 10^6 space makes a plain SHA-256 trivially reversible by anyone
    who can read the Valkey value."""
    key = get_settings().secret_key.encode("utf-8")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_token(nbytes: int = 32) -> str:
    """A URL-safe random token (session ids, challenge ids)."""
    return secrets.token_urlsafe(nbytes)


def constant_time_equals(a: str, b: str) -> bool:
    """Timing-safe string comparison (OTP code checks)."""
    return hmac.compare_digest(a, b)
