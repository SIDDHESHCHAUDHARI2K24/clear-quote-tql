"""Idempotent dev-user seed (CQ-014 AC8 / Decision #2).

Run via `uv run python backend/scripts/seed_dev_users.py` from the repo
root. Reads the shared demo password from `DEMO_STAFF_PASSWORD`
(`Settings.demo_staff_password`) rather than a flag, so it's the same seed
command in every dev environment; exits non-zero with a clear message if
that env var isn't set (unset in prod-like envs by design). Safe to run
more than once — `seed_dev_users` leaves existing rows untouched.
"""

import asyncio
import sys

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.features.auth.users.service import seed_dev_users


async def _run() -> None:
    settings = get_settings()
    if not settings.demo_staff_password:
        print(
            "DEMO_STAFF_PASSWORD is not set — refusing to seed dev users. "
            "Set it in this worktree's .env (local/dev only).",
            file=sys.stderr,
        )
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        users = await seed_dev_users(db, password=settings.demo_staff_password)
        await db.commit()
        for user in users:
            print(f"{user.email} ({user.role.value})")


if __name__ == "__main__":
    asyncio.run(_run())
