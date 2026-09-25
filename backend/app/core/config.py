"""App-wide settings, read once and shared via `get_settings()`.

Every module reads configuration through `get_settings()`; nothing else in
the codebase should instantiate `Settings()` directly (it would bypass the
`lru_cache` and could read stale/mismatched values across modules).
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str
    secret_key: str

    database_url: str
    test_database_url: str

    # CQ-007: Fernet key (`Fernet.generate_key()` format) for encrypting
    # `application_parties.ssn_encrypted` at rest. Optional in the type
    # because APP_ENV=test may not set one (see the validator below); every
    # other environment must set it.
    field_encryption_key: str | None = None

    valkey_url: str

    s3_endpoint: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str

    smtp_host: str
    smtp_port: int
    smtp_from: str

    temporal_address: str
    temporal_namespace: str
    temporal_task_queue: str

    cors_origins: Annotated[list[str], NoDecode] = []

    # CQ-009: shared mock-adapter latency simulation. `integration_latency_enabled`
    # reads `INTEGRATION_LATENCY_ENABLED` (pydantic-settings' default env-var
    # name for this field); `backend/conftest.py` sets it to "false" for the
    # whole pytest session so tests stay fast, except `integrations/common/
    # tests/test_latency.py`'s enabled-path test, which flips it back via
    # `get_settings()` monkeypatching for that one test.
    integration_latency_min_ms: int = 200
    integration_latency_max_ms: int = 1200
    integration_latency_enabled: bool = True

    # CQ-013: fixed dev LO id `deps.get_current_lo_stub()` returns until
    # CQ-014 replaces it with real staff auth. Unset -> every pricing route
    # raises `AuthenticationError` (401).
    dev_lo_id: str | None = None

    # CQ-010 (review round 1, finding #3): shared demo password
    # `seed/loader.py::seed_users` bcrypt-hashes for the seeded staff users.
    # No default -- deliberately never committed as a literal anywhere in
    # the repo. `make demo-reset` fails fast with a clear message if unset.
    seed_staff_password: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow `CORS_ORIGINS` to be a comma-separated string in `.env`.

        `NoDecode` above stops pydantic-settings from eagerly JSON-decoding
        this env var (which would fail on a raw comma-separated string)
        before this validator gets a chance to run.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_field_encryption_key_outside_test(self) -> "Settings":
        """AC4: fail fast at startup rather than at first SSN read/write.

        `backend/conftest.py` sets `APP_ENV=test` for the whole pytest
        session, so tests that don't care about encryption never need to
        set a key; every other environment (local/CI/prod) must have one.
        """
        if self.app_env != "test" and not self.field_encryption_key:
            raise ValueError(
                "FIELD_ENCRYPTION_KEY must be set when APP_ENV is not 'test' "
                "(generate one with `Fernet.generate_key()`)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
