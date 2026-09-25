"""DB session plumbing for Temporal activities.

Activities can't take a live `AsyncSession` as an argument — Temporal
serializes activity inputs/outputs, and in a real deployment the worker
runs in a separate process from whatever started the workflow — so every
activity opens its own session via `session_factory()`. Production points
this at `app.core.db.AsyncSessionLocal`; `backend/app/workflows/tests/
conftest.py` monkeypatches the `session_factory` *attribute on this
module* (not a name imported by value elsewhere, so the patch takes effect
for every subsequent call) to bind sessions to the test's own already-open
connection/transaction, so activity writes are visible to test assertions
and roll back with the rest of `db_session`'s isolation (plan.md #12).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal

session_factory: Callable[[], AsyncSession] = AsyncSessionLocal
