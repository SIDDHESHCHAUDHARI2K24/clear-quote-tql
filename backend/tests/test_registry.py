"""AC5: appending a dotted path to `FEATURE_ROUTERS` registers its routes
without touching `main.py`."""

import pytest
from fastapi.testclient import TestClient

from app.core import registry
from app.main import create_app


def test_dummy_router_registers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        registry,
        "FEATURE_ROUTERS",
        [*registry.FEATURE_ROUTERS, "tests._dummy_feature_router"],
    )

    app = create_app()

    assert "/api/v1/dummy" in app.openapi()["paths"]


def test_health_is_unprefixed_only_not_also_under_api_v1() -> None:
    """`/health` is mounted directly on `app` and never through the
    registry: `system` is not in `FEATURE_ROUTERS`, so `/api/v1/health`
    must not exist, live or in the OpenAPI schema."""
    app = create_app()

    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/api/v1/health" not in paths

    client = TestClient(app)
    assert client.get("/health").status_code in (200, 503)
    assert client.get("/api/v1/health").status_code == 404
