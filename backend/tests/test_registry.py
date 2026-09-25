"""AC5: appending a dotted path to `FEATURE_ROUTERS` registers its routes
without touching `main.py`."""

import pytest

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


def test_system_router_is_mounted_unprefixed_and_registered() -> None:
    app = create_app()

    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/api/v1/health" in paths
