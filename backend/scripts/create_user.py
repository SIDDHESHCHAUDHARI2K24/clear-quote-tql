"""CLI to create one staff `User` row (CQ-014 Decision #2).

Run via `uv run python backend/scripts/create_user.py --email ... --role
{lo,manager,admin} --full-name ...` from the repo root. Password comes from
`--password`, or an interactive `getpass` prompt if omitted (so it never
lands in shell history by default).
"""

import argparse
import asyncio
import getpass

from app.core.db import AsyncSessionLocal
from app.core.enums import UserRole
from app.features.auth.users.service import create_user


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create one staff user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=["lo", "manager", "admin"])
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--nmls", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--phone", default=None)
    parser.add_argument("--password", default=None, help="Prompted via getpass if omitted.")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Password: ")
    async with AsyncSessionLocal() as db:
        user = await create_user(
            db,
            email=args.email,
            password=password,
            role=UserRole(args.role),
            full_name=args.full_name,
            nmls=args.nmls,
            title=args.title,
            phone=args.phone,
        )
        await db.commit()
        print(f"Created user {user.email} ({user.role.value}) id={user.id}")


if __name__ == "__main__":
    asyncio.run(_run(_parse_args()))
