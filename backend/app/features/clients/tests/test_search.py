"""`GET /api/v1/clients?q=` (spec.md AC1)."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.features.clients.tests.conftest import MakeApplicationFor, MakeClient


async def test_client_search(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    """AC1: "hale" returns Marcus Hale; a partial, case-insensitive email
    substring returns its client too."""
    await make_staff_session(UserRole.MANAGER)

    marcus = await make_client(full_name="Marcus Hale", email="marcus.hale@clearquote-demo.test")
    await make_application_for(marcus.client, marcus.lo)
    other = await make_client(full_name="Priya Nair", email="priya.nair@clearquote-demo.test")
    await make_application_for(other.client, other.lo)
    await db_session.flush()

    resp = await client.get("/api/v1/clients", params={"q": "hale"})
    assert resp.status_code == 200, resp.text
    ids = {uuid.UUID(item["id"]) for item in resp.json()["items"]}
    assert ids == {marcus.client.id}

    # Case-insensitive.
    resp = await client.get("/api/v1/clients", params={"q": "HALE"})
    assert {uuid.UUID(item["id"]) for item in resp.json()["items"]} == {marcus.client.id}

    # A partial email substring.
    resp = await client.get("/api/v1/clients", params={"q": "priya.nair@clear"})
    assert {uuid.UUID(item["id"]) for item in resp.json()["items"]} == {other.client.id}

    # No match.
    resp = await client.get("/api/v1/clients", params={"q": "nobody-here"})
    assert resp.json()["items"] == []
