import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.core.db import Base

# Every feature/integration `models.py` must be imported before
# `target_metadata` is read below, or `Base.metadata` won't know about its
# tables and `--autogenerate` will silently propose dropping them (and a
# bare `create_all`/`upgrade head` on an empty metadata would build nothing).
# CQ-007 onward: add a new models module's import here the same commit it's
# created in.
import app.features.auth.models  # noqa: E402,F401
import app.features.applications.models  # noqa: E402,F401
import app.features.applications.assets.models  # noqa: E402,F401
import app.features.applications.credit.models  # noqa: E402,F401
import app.features.applications.housing.models  # noqa: E402,F401
import app.features.applications.property.models  # noqa: E402,F401
import app.features.applications.timeline.models  # noqa: E402,F401
import app.features.applications.verification.models  # noqa: E402,F401
import app.features.borrower.consent.models  # noqa: E402,F401
import app.features.clients.models  # noqa: E402,F401
import app.features.notifications.outbox.models  # noqa: E402,F401
import app.features.pricing.scenarios.models  # noqa: E402,F401
import app.features.quotes.builder.models  # noqa: E402,F401
import app.features.quotes.send.models  # noqa: E402,F401
import app.features.settings.models  # noqa: E402,F401
import app.integrations.common.models  # noqa: E402,F401
import app.integrations.credit.models  # noqa: E402,F401
import app.integrations.crm.models  # noqa: E402,F401
import app.integrations.insurance.models  # noqa: E402,F401
import app.integrations.los.models  # noqa: E402,F401
import app.integrations.pricing.models  # noqa: E402,F401
import app.integrations.property_search.models  # noqa: E402,F401
import app.integrations.rent.models  # noqa: E402,F401
import app.integrations.str.models  # noqa: E402,F401
import app.integrations.tax.models  # noqa: E402,F401

# this is the Alembic Config object, which provides access to values within
# the .ini file in use.
config = context.config

# Interpret the config file for Python logging (from alembic.ini).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Set the DB URL at runtime from settings instead of alembic.ini, so the same
# migration config works locally, in CI and in production without editing the
# ini file. `config.attributes["sqlalchemy_url"]` is alembic's documented way
# for a caller (e.g. `backend/conftest.py`, targeting `TEST_DATABASE_URL`) to
# override this programmatically instead of via `get_settings().database_url`.
config.set_main_option(
    "sqlalchemy.url", config.attributes.get("sqlalchemy_url") or get_settings().database_url
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    `DATABASE_URL` uses the `postgresql+asyncpg` driver (the same one the
    app uses), which a plain sync `engine_from_config`/`create_engine` can't
    load — asyncpg is async-only. This uses Alembic's standard async recipe
    instead: an async engine, with the actual migration run handed to
    `connection.run_sync(...)`.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
