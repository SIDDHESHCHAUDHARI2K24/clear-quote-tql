"""At-rest encryption for sensitive columns (currently just SSN).

`EncryptedString` is a SQLAlchemy `TypeDecorator` over `LargeBinary`:
plaintext goes in on bind (INSERT/UPDATE), a Fernet token is what actually
hits Postgres, and it is decrypted back to plaintext on read. A raw SQL
query that bypasses the ORM sees only ciphertext.

The key is `Settings.field_encryption_key`, sourced from the
`FIELD_ENCRYPTION_KEY` env var (a `Fernet.generate_key()`-format, 32-byte
urlsafe-base64 string). `core/config.py` fails fast at `get_settings()` time
if it's unset outside `APP_ENV=test`.
"""

from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().field_encryption_key
    if not key:
        # Only reachable in APP_ENV=test without a key configured (the
        # config fail-fast lets this slide so unit tests that never touch
        # `application_parties` don't need a key); tests that exercise
        # encryption set FIELD_ENCRYPTION_KEY explicitly.
        raise RuntimeError("FIELD_ENCRYPTION_KEY is not set; cannot encrypt/decrypt SSN columns.")
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_str(value: str) -> str:
    """Fernet token (urlsafe base64 text) for `value`, for ciphertext kept
    outside an `EncryptedString` column, e.g. inside a JSONB document."""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    """Inverse of `encrypt_str`."""
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


class EncryptedString(TypeDecorator[str]):
    """Encrypts a UTF-8 string to a Fernet token before storing as bytes."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> bytes | None:
        if value is None:
            return None
        return _fernet().encrypt(value.encode("utf-8"))

    def process_result_value(self, value: bytes | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return _fernet().decrypt(bytes(value)).decode("utf-8")
