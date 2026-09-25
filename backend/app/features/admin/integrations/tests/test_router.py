"""spec.md AC5: `GET/PUT /admin/integrations` -- admin-only, summary shape,
and the force-failure toggle. AC4's full pipeline effect is covered in
`backend/app/workflows/tests/test_admin_forced_pricing_failure.py`
(plan.md: needs the Temporal test env, whose fixtures live there)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.enums import UserRole
from app.integrations.common.models import IntegrationCall
from conftest import StaffSession


async def test_integrations_401_without_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/integrations")
    assert response.status_code == 401


async def test_integrations_admin_only(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await make_staff_session(role=UserRole.LO)
    lo_response = await client.get("/api/v1/admin/integrations")
    assert lo_response.status_code == 403

    await make_staff_session(role=UserRole.MANAGER)
    manager_response = await client.get("/api/v1/admin/integrations")
    assert manager_response.status_code == 403

    await make_staff_session(role=UserRole.ADMIN)
    admin_response = await client.get("/api/v1/admin/integrations")
    assert admin_response.status_code == 200


async def test_integrations_summary_shape(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
    make_integration_call: Callable[..., Awaitable[IntegrationCall]],
) -> None:
    now = datetime.now(UTC)
    await make_integration_call("pricing", success=True, latency_ms=412, called_at=now)
    await make_integration_call(
        "pricing",
        success=False,
        error_code="PROVIDER_UNAVAILABLE",
        called_at=now - timedelta(minutes=5),
    )
    # Outside the last-hour window -- must not count toward `calls_last_hour`.
    await make_integration_call("pricing", success=True, called_at=now - timedelta(hours=2))

    await make_staff_session(role=UserRole.ADMIN)
    response = await client.get("/api/v1/admin/integrations")
    assert response.status_code == 200
    adapters = {row["adapter"]: row for row in response.json()["adapters"]}

    assert set(adapters) == {
        "credit",
        "crm",
        "insurance",
        "los",
        "pricing",
        "property_search",
        "rent",
        "str",
        "tax",
    }

    pricing = adapters["pricing"]
    assert pricing["provider"] == "Optimal Blue"
    assert pricing["last_result"] == "ok"  # most recent call was a success
    assert pricing["last_latency_ms"] == 412
    assert pricing["calls_last_hour"] == 2
    assert pricing["force_failure"] is False

    never_called = adapters["crm"]
    assert never_called["last_call_at"] is None
    assert never_called["last_result"] == "never_called"
    assert never_called["calls_last_hour"] == 0


async def test_toggle_force_failure(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await make_staff_session(role=UserRole.LO)
    lo_response = await client.put(
        "/api/v1/admin/integrations/pricing", json={"force_failure": True}
    )
    assert lo_response.status_code == 403

    await make_staff_session(role=UserRole.ADMIN)
    response = await client.put("/api/v1/admin/integrations/pricing", json={"force_failure": True})
    assert response.status_code == 200
    assert response.json()["force_failure"] is True

    status_response = await client.get("/api/v1/admin/integrations")
    pricing = next(row for row in status_response.json()["adapters"] if row["adapter"] == "pricing")
    assert pricing["force_failure"] is True

    off_response = await client.put(
        "/api/v1/admin/integrations/pricing", json={"force_failure": False}
    )
    assert off_response.json()["force_failure"] is False


async def test_toggle_unknown_adapter_404(
    client: AsyncClient,
    make_staff_session: Callable[..., Awaitable[StaffSession]],
) -> None:
    await make_staff_session(role=UserRole.ADMIN)
    response = await client.put(
        "/api/v1/admin/integrations/not-a-real-adapter", json={"force_failure": True}
    )
    assert response.status_code == 404
