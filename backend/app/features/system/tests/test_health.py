"""AC1/AC2: `/health` reports every backing service and the pinned shape."""

import pytest
from httpx import AsyncClient

from app.features.system import service
from app.features.system.schemas import CheckResult


def _passing_check(name: str) -> object:
    """Builds a fake `check_*` replacement that always reports "ok".

    Per CQ-004's spec.md: in CI only Postgres runs as a real service
    container, so Valkey/MinIO/Temporal are exercised by monkeypatching
    their clients rather than requiring three more service containers.
    """

    async def _check(*_args: object, **_kwargs: object) -> CheckResult:
        return CheckResult(name=name, status="ok")

    return _check


def _patch_non_db_checks_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "check_valkey", _passing_check("valkey"))
    monkeypatch.setattr(service, "check_minio", _passing_check("minio"))
    monkeypatch.setattr(service, "check_temporal", _passing_check("temporal"))


async def test_health_ok(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_non_db_checks_ok(monkeypatch)

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
    _patch_non_db_checks_ok(monkeypatch)

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
