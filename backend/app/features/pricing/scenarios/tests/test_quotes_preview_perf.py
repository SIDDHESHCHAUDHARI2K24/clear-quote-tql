"""AC1: `/quotes/preview` is engine-only (no adapter latency, no
persistence) and responds under 300ms, returning the same numbers
`compute_quote` computes.
"""

import json
import time
from decimal import Decimal

from httpx import AsyncClient

from app.features.pricing.engine.quote_engine import compute_quote
from app.features.pricing.engine.types import ConfigSnapshot, ScenarioInputs, StrategyType

_REQUEST = {
    "purchase_price": "225000.00",
    "down_payment_pct": "0.20",
    "note_rate": "0.07125",
    "strategy": "PRIMARY",
    "fico": 780,
    "property_tax_annual_rate": "0.01",
    "insurance_annual_rate": "0.005",
}


async def test_preview_matches_compute_quote(client: AsyncClient) -> None:
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


async def test_preview_responds_under_300ms(client: AsyncClient) -> None:
    started = time.perf_counter()
    response = await client.post("/api/v1/quotes/preview", json=_REQUEST)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 300, f"took {elapsed_ms:.1f}ms"


async def test_preview_investment_ltr_includes_dscr(client: AsyncClient) -> None:
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
