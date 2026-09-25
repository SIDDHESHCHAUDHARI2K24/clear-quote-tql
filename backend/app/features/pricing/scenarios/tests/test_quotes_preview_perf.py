"""AC1: `/quotes/preview` is engine-only (no adapter latency, no
persistence) and responds under 300ms, returning the same numbers
`compute_quote` computes.

CQ-017: the route now requires a signed-in staff user (it was previously
reachable with no auth at all) -- every test here logs in via
`make_staff_session` first.
"""

import json
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient

from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType
from conftest import StaffSession

_REQUEST = {
    "purchase_price": "225000.00",
    "down_payment_pct": "0.20",
    "note_rate": "0.07125",
    "strategy": "PRIMARY",
    "fico": 780,
    "property_tax_annual_rate": "0.01",
    "insurance_annual_rate": "0.005",
}


async def test_preview_requires_staff_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/quotes/preview", json=_REQUEST)
    assert response.status_code == 401


async def test_preview_matches_compute_quote(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    await make_staff_session()
    response = await client.post("/api/v1/quotes/preview", json=_REQUEST)
    assert response.status_code == 200

    expected = compute_quote(
        ScenarioInputs(
            purchase_price=Decimal("225000.00"),
            down_payment_pct=Decimal("0.20"),
            note_rate=Decimal("0.07125"),
            strategy=StrategyType.PRIMARY,
            fico=780,
            property_tax_annual_rate=Decimal("0.01"),
            insurance_annual_rate=Decimal("0.005"),
        ),
        ConfigSnapshot(),
    )
    expected_json = json.loads(expected.model_dump_json())

    body = response.json()
    assert Decimal(body["loan_amount"]) == Decimal(expected_json["loan_amount"])
    assert Decimal(body["monthly_pi"]) == Decimal(expected_json["monthly_pi"])
    assert Decimal(body["cash_to_close"]) == Decimal(expected_json["cash_to_close"])
    assert body["dscr_bucket"] is None  # primary never carries DSCR


async def test_preview_responds_under_300ms(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    await make_staff_session()
    started = time.perf_counter()
    response = await client.post("/api/v1/quotes/preview", json=_REQUEST)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 300, f"took {elapsed_ms:.1f}ms"


async def test_preview_investment_ltr_includes_dscr(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    await make_staff_session()
    request = {
        **_REQUEST,
        "strategy": "LTR",
        "down_payment_pct": "0.25",
        "market_rent_ltr": "2200.00",
    }
    response = await client.post("/api/v1/quotes/preview", json=request)

    assert response.status_code == 200
    body = response.json()
    assert body["dscr_bucket"] is not None
    assert body["dscr_ratio"] is not None


async def test_preview_accepts_down_payment_amount(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    """CQ-017 AC2: the linked %/$ down-payment input can send either side."""
    await make_staff_session()
    request = {k: v for k, v in _REQUEST.items() if k != "down_payment_pct"}
    request["down_payment_amount"] = "45000.00"  # 20.00% of 225000.00
    response = await client.post("/api/v1/quotes/preview", json=request)

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["down_payment_pct"]) == Decimal("0.2000")
    assert Decimal(body["down_payment_amount"]) == Decimal("45000.00")
    assert Decimal(body["loan_amount"]) == Decimal("180000.00")
    # Regression pin: the amount-based path's resolved `down_payment_pct`
    # and the engine's own `ltv_pct` always agree (sum to 1) at the
    # engine's own rounding -- both come from the same `compute_quote`
    # call, never independently derived.
    assert Decimal(body["down_payment_pct"]) + Decimal(body["ltv_pct"]) == Decimal("1.0000")


async def test_preview_rejects_both_or_neither_down_payment_field(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    await make_staff_session()
    both = {**_REQUEST, "down_payment_amount": "45000.00"}
    response = await client.post("/api/v1/quotes/preview", json=both)
    assert response.status_code == 422

    neither = {k: v for k, v in _REQUEST.items() if k != "down_payment_pct"}
    response = await client.post("/api/v1/quotes/preview", json=neither)
    assert response.status_code == 422


async def test_preview_down_payment_amount_with_zero_price_is_422_not_500(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    """Review finding: a zero/negative purchase_price with down_payment_
    amount must never reach a bare ZeroDivisionError/500."""
    await make_staff_session()
    request = {k: v for k, v in _REQUEST.items() if k != "down_payment_pct"}
    request["purchase_price"] = "0.00"
    request["down_payment_amount"] = "45000.00"
    response = await client.post("/api/v1/quotes/preview", json=request)
    assert response.status_code == 422


async def test_preview_down_payment_amount_with_invalid_price_is_422_not_500(
    client: AsyncClient, make_staff_session: Callable[..., Awaitable[StaffSession]]
) -> None:
    """Review finding: a non-decimal purchase_price with down_payment_
    amount must degrade to a normal 422, not an unhandled InvalidOperation
    500."""
    await make_staff_session()
    request = {k: v for k, v in _REQUEST.items() if k != "down_payment_pct"}
    request["purchase_price"] = "not-a-number"
    request["down_payment_amount"] = "45000.00"
    response = await client.post("/api/v1/quotes/preview", json=request)
    assert response.status_code == 422
