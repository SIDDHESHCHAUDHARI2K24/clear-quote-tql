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


async def test_client_search_escapes_like_wildcards(
    client: AsyncClient,
    db_session: AsyncSession,
    make_staff_session: Any,
    make_client: MakeClient,
    make_application_for: MakeApplicationFor,
) -> None:
    """Review round 1: `q` used to build an unescaped ILIKE pattern, so a
    literal `%`/`_` in the search text matched everything instead of
    matching literally (same fix as the outbox's own `q`)."""
    await make_staff_session(UserRole.MANAGER)

    foo_bar = await make_client(full_name="foo_bar Client", email=f"{uuid.uuid4()}@example.test")
    await make_application_for(foo_bar.client, foo_bar.lo)
    foo_x_bar = await make_client(full_name="fooXbar Client", email=f"{uuid.uuid4()}@example.test")
    await make_application_for(foo_x_bar.client, foo_x_bar.lo)
    percent = await make_client(full_name="100% Client", email=f"{uuid.uuid4()}@example.test")
    await make_application_for(percent.client, percent.lo)
    await db_session.flush()

    # A literal "_" must not act as a single-character wildcard: "foo_bar"
    # matches only the client actually named "foo_bar Client", not
    # "fooXbar Client" too.
    resp = await client.get("/api/v1/clients", params={"q": "foo_bar"})
    assert {uuid.UUID(item["id"]) for item in resp.json()["items"]} == {foo_bar.client.id}

    # A literal "%" must not act as a wildcard matching every row.
    resp = await client.get("/api/v1/clients", params={"q": "100%"})
    assert {uuid.UUID(item["id"]) for item in resp.json()["items"]} == {percent.client.id}
