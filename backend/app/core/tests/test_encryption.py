"""AC4: SSN ciphertext at rest, and `FIELD_ENCRYPTION_KEY` fail-fast outside
`APP_ENV=test`."""

import uuid

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import Occupancy, UserRole
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.auth.models import User
from app.features.clients.models import Client

PLAINTEXT_SSN = "123-45-6789"


def _settings(app_env: str, field_encryption_key: str | None) -> Settings:
    """Builds a `Settings` instance with every other field pinned to a
    throwaway value, varying only what each test below cares about."""
    return Settings(
        app_env=app_env,
        field_encryption_key=field_encryption_key,
        secret_key="x",
        database_url="postgresql+asyncpg://x/x",
        test_database_url="postgresql+asyncpg://x/x",
        valkey_url="redis://x",
        s3_endpoint="http://x",
        s3_bucket="x",
        s3_access_key="x",
        s3_secret_key="x",
        s3_region="us-east-1",
        smtp_host="x",
        smtp_port=1025,
        smtp_from="a@b.com",
        temporal_address="x",
        temporal_namespace="default",
        temporal_task_queue="x",
    )


async def _make_application(db_session: AsyncSession) -> uuid.UUID:
    lo = User(
        email=f"lo-{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.LO,
        full_name="Test LO",
    )
    db_session.add(lo)
    await db_session.flush()

    client = Client(
        full_name="Test Client",
        email=f"client-{uuid.uuid4()}@example.com",
        assigned_lo_id=lo.id,
    )
    db_session.add(client)
    await db_session.flush()

    application = Application(client_id=client.id, lo_id=lo.id, occupancy=Occupancy.PRIMARY)
    db_session.add(application)
    await db_session.flush()
    return application.id


async def test_ssn_is_ciphertext_via_raw_sql_but_plaintext_via_orm(
    db_session: AsyncSession,
) -> None:
    application_id = await _make_application(db_session)

    party = ApplicationParty(
        application_id=application_id,
        role=PartyRole.BORROWER,
        first_name="Jane",
        last_name="Doe",
        ssn_encrypted=PLAINTEXT_SSN,
    )
    db_session.add(party)
    await db_session.commit()

    raw_value: bytes = (
        await db_session.execute(
            text("SELECT ssn_encrypted FROM application_parties WHERE id = :id"),
            {"id": party.id},
        )
    ).scalar_one()
    raw_bytes = bytes(raw_value)

    # Bypassing the ORM (raw SQL) must never expose the plaintext digits.
    assert PLAINTEXT_SSN.encode("utf-8") not in raw_bytes
    # It's real Fernet ciphertext for the configured key, not just any bytes.
    key = get_settings().field_encryption_key
    assert key is not None
    assert Fernet(key.encode("utf-8")).decrypt(raw_bytes) == PLAINTEXT_SSN.encode("utf-8")

    # The ORM (EncryptedString.process_result_value) decrypts transparently.
    await db_session.refresh(party)
    assert party.ssn_encrypted == PLAINTEXT_SSN


def test_settings_requires_field_encryption_key_outside_test_env() -> None:
    with pytest.raises(ValidationError):
        _settings(app_env="local", field_encryption_key=None)


def test_settings_allows_missing_key_in_test_env() -> None:
    settings = _settings(app_env="test", field_encryption_key=None)
    assert settings.field_encryption_key is None
