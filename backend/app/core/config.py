"""App-wide settings, read once and shared via `get_settings()`.

Every module reads configuration through `get_settings()`; nothing else in
the codebase should instantiate `Settings()` directly (it would bypass the
`lru_cache` and could read stale/mismatched values across modules).
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str
    secret_key: str

    database_url: str
    test_database_url: str

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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
