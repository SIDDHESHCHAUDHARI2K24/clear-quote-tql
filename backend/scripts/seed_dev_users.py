"""Idempotent dev-user seed (CQ-014 AC8 / Decision #2; CQ-015 AC8 /
Decision #12).

Run via `uv run python backend/scripts/seed_dev_users.py` from the repo
root. Reads the shared demo passwords from `DEMO_STAFF_PASSWORD` and
`DEMO_BORROWER_PASSWORD` (`Settings.demo_staff_password` /
`.demo_borrower_password`) rather than flags, so it's the same seed command
in every dev environment; exits non-zero with a clear message if
`DEMO_STAFF_PASSWORD` isn't set (unset in prod-like envs by design).
Borrower seeding only runs when `DEMO_BORROWER_PASSWORD` is also set — it's
optional so a staff-only environment doesn't need it. Safe to run more than
once — `seed_dev_users`/`seed_dev_borrowers` leave existing rows untouched.
"""

import asyncio
import sys

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.features.auth.users.service import seed_dev_borrowers, seed_dev_users


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

        if settings.demo_borrower_password:
            accounts = await seed_dev_borrowers(db, password=settings.demo_borrower_password)
            await db.commit()
            for account in accounts:
                print(f"{account.email} (borrower)")


if __name__ == "__main__":
    asyncio.run(_run())
