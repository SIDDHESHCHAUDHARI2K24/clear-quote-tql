"""AC1/AC2: `/health` reports every backing service and the pinned shape."""

import pytest
from httpx import AsyncClient

from app.features.system import service
from app.features.system.schemas import CheckResult


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "checks": {
            "database": "ok",
            "valkey": "ok",
            "minio": "ok",
            "temporal": "ok",
        },
    }


async def test_health_degraded(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _failing_valkey_check(valkey_url: str) -> CheckResult:
        return CheckResult(name="valkey", status="error: connection refused")

    monkeypatch.setattr(service, "check_valkey", _failing_valkey_check)

    response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["valkey"] == "error: connection refused"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["minio"] == "ok"
    assert body["checks"]["temporal"] == "ok"
