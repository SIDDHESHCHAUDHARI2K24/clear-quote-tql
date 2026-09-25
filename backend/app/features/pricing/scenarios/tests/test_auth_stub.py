"""AC11: every pricing route is reachable without credentials (stub
dependency) and raises CQ-004's `AuthenticationError` (401,
`AUTHENTICATION_ERROR`) only when `DEV_LO_ID` is unset.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError
from app.features.pricing.scenarios.deps import get_current_lo_stub


def test_get_current_lo_stub_returns_dev_lo_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_id = uuid.uuid4()
    settings = get_settings().model_copy(update={"dev_lo_id": str(fixed_id)})
    monkeypatch.setattr("app.features.pricing.scenarios.deps.get_settings", lambda: settings)

    assert get_current_lo_stub() == fixed_id


def test_get_current_lo_stub_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"dev_lo_id": None})
    monkeypatch.setattr("app.features.pricing.scenarios.deps.get_settings", lambda: settings)

    with pytest.raises(AuthenticationError) as exc_info:
        get_current_lo_stub()
    assert exc_info.value.code == "AUTHENTICATION_ERROR"
    assert exc_info.value.status_code == 401


async def test_products_route_is_401_when_dev_lo_id_unset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    unset_settings = get_settings().model_copy(update={"dev_lo_id": None})
    monkeypatch.setattr("app.features.pricing.scenarios.deps.get_settings", lambda: unset_settings)

    response = await client.get(f"/api/v1/scenarios/{uuid.uuid4()}/products")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


async def test_preview_route_needs_no_credentials_header(client: AsyncClient) -> None:
    """`/quotes/preview` doesn't even depend on the stub (spec.md: engine
    only) -- reachable with zero setup, no `Authorization` header."""
    response = await client.post(
        "/api/v1/quotes/preview",
        json={
            "purchase_price": "225000.00",
            "down_payment_pct": "0.20",
            "note_rate": "0.07125",
            "strategy": "PRIMARY",
            "fico": 780,
            "property_tax_annual_rate": "0.01",
            "insurance_annual_rate": "0.005",
        },
    )
    assert response.status_code == 200


def test_settings_type_still_has_dev_lo_id_field() -> None:
    assert "dev_lo_id" in Settings.model_fields
