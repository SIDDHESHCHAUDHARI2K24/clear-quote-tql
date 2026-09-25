"""`make demo-reset` entrypoint: `uv run python -m seed.reset`.

Drops and recreates the `public` schema on `DATABASE_URL` (cq_dev only --
never `cq_test` or the `temporal` database, which live in the same Postgres
instance but are separate databases entirely untouched by this script),
runs `alembic upgrade head`, seeds users/providers/personas/background
applications, and prints a timing summary. Budget: under 60s (AC1).

`SEED_FAST_ADAPTERS` (default `1`) must be resolved, and its effect
(`INTEGRATION_LATENCY_ENABLED=false`) set in `os.environ`, before anything
below imports `app.core.config` -- `get_settings()` is `@lru_cache`d, so
whatever `Settings` sees on its first construction is final for the whole
process (plan.md decision #5).
"""

from __future__ import annotations

import os


def _configure_env() -> None:
    fast_adapters = os.environ.get("SEED_FAST_ADAPTERS", "1") != "0"
    if fast_adapters:
        os.environ["INTEGRATION_LATENCY_ENABLED"] = "false"


_configure_env()

import asyncio  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from seed.config import load_seed_config  # noqa: E402
from seed.generators.background_applications import seed_background_applications  # noqa: E402
from seed.generators.documents import ensure_demo_docs_bucket, get_s3_client  # noqa: E402
from seed.loader import (  # noqa: E402
    MissingStaffPasswordError,
    PersonaSeedResult,
    _staff_password,  # noqa: E402
    load_persona_fixtures,
    seed_persona,
    seed_providers,
    seed_users,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


async def _drop_and_recreate_schema(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def _upgrade_to_head(database_url: str) -> None:
    alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    alembic_cfg.attributes["sqlalchemy_url"] = database_url
    command.upgrade(alembic_cfg, "head")


async def _seed_everything() -> dict[str, Any]:
    from app.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user_result = await seed_users(db)
        await seed_providers(db)

        s3_client = get_s3_client()
        ensure_demo_docs_bucket(s3_client)

        personas = load_persona_fixtures()
        persona_results: list[PersonaSeedResult] = []
        for i, persona in enumerate(personas):
            lo_id = user_result.lo_ids[i % len(user_result.lo_ids)]
            result = await seed_persona(db, persona, lo_id=lo_id, s3_client=s3_client)
            persona_results.append(result)

        seed_config = load_seed_config()
        markets = [p["market"] for p in personas]
        background_summary = await seed_background_applications(
            db,
            rng_seed=seed_config.rng_seed,
            lo_ids=user_result.lo_ids,
            markets=markets,
        )

    return {
        "users": user_result,
        "personas": persona_results,
        "background": background_summary,
    }


def main() -> None:
    # Fail fast, before any destructive DB operation (review round 1,
    # finding #3): a missing SEED_STAFF_PASSWORD should never leave cq_dev
    # half-reset.
    try:
        _staff_password()
    except MissingStaffPasswordError as exc:
        print(f"demo-reset: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    start = time.monotonic()
    database_url = get_settings().database_url

    asyncio.run(_drop_and_recreate_schema(database_url))
    _upgrade_to_head(database_url)
    summary = asyncio.run(_seed_everything())

    elapsed = time.monotonic() - start

    persona_results: list[PersonaSeedResult] = summary["personas"]
    any_pricing_ran = any(r.pricing_ran for r in persona_results)

    print("=== demo-reset summary ===")
    print(f"elapsed: {elapsed:.1f}s")
    print(f"users seeded: {len(summary['users'].by_key)} (2 LO, 1 Manager, 1 Admin)")
    print(f"personas seeded: {len(persona_results)}")
    for r in persona_results:
        print(f"  {r.key}: {r.final_status.value}")
    if not any_pricing_ran:
        print(
            "NOTE: pricing stage SKIPPED for every persona -- CQ-013's "
            "pricing.enrichment/scenarios/quotes.builder service functions "
            "are not merged yet (seed/pricing_seam.py). Personas with no LOS "
            "or housing defect stopped at 'ready_to_price'; Aisha Coleman's "
            "'missing Occupancy' flag and Grace Kim/Luis Romero's sent/"
            "option_selected fixture layer land once CQ-013 merges."
        )
    background_summary = summary["background"]
    print(f"background applications: {background_summary.total_created}")
    print(f"  by status: {background_summary.by_status}")
    print(f"  by lo: {background_summary.by_lo}")
    print(f"=== done in {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
