"""Fixtures for `portal/apply/tests` (CQ-032a).

- `stub_storage`: an in-memory S3 stand-in behind `core.storage.get_client`.
- `sent_emails`: captures `smtp_send` (the outbox row is still written).
- `tampa_listing`: one Tampa, FL listing so the metro picker and the TBD
  property resolution have a market to work with.
- `fake_temporal`: overrides the router's Temporal client factory with a
  recorder, so submit tests never need a Temporal server.
- `valid_tabs()`: a complete, valid set of the four tabs (Tampa STR, TBD).
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.features.applications.property.models import PropertyType
from app.features.notifications.email import service as email_service
from app.features.portal.apply import router as apply_router
from app.integrations.property_search.models import DealGrade, ProviderListing

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class StubS3:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def head_bucket(self, *, Bucket: str) -> None:  # noqa: N803
        if Bucket not in self.buckets:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, *, Bucket: str) -> None:  # noqa: N803
        self.buckets.add(Bucket)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:  # noqa: N803
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        body, content_type = self.objects[(Bucket, Key)]

        class _Body:
            def read(self) -> bytes:
                return body

            def close(self) -> None:
                return None

        return {"Body": _Body(), "ContentType": content_type}

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        self.objects.pop((Bucket, Key), None)

    def keys(self) -> list[str]:
        return sorted(key for _, key in self.objects)


@pytest.fixture
def stub_storage(monkeypatch: pytest.MonkeyPatch) -> StubS3:
    stub = StubS3()
    monkeypatch.setattr(storage, "get_client", lambda: stub)
    return stub


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str


@pytest.fixture
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[SentEmail]:
    sent: list[SentEmail] = []

    async def _fake_smtp_send(*, to: str, subject: str, html: str) -> None:
        sent.append(SentEmail(to=to, subject=subject, html=html))

    monkeypatch.setattr(email_service, "smtp_send", _fake_smtp_send)
    return sent


@pytest_asyncio.fixture
async def tampa_listing(db_session: AsyncSession) -> ProviderListing:
    listing = ProviderListing(
        address="101 Sample St",
        city="Tampa",
        state="FL",
        zip="33602",
        county="Hillsborough",
        metro="Tampa",
        list_price=Decimal("290700"),
        beds=3,
        baths=Decimal("2.0"),
        sqft=1650,
        property_type=PropertyType.SINGLE_FAMILY,
        image_url="https://example.test/a.jpg",
        deal_grade=DealGrade.GREAT_BUY,
        str_permitted=True,
    )
    db_session.add(listing)
    await db_session.commit()
    return listing


@dataclass
class FakeTemporal:
    started: list[dict[str, Any]] = field(default_factory=list)
    fail: bool = False

    async def start_workflow(self, *args: Any, **kwargs: Any) -> None:
        if self.fail:
            raise RuntimeError("temporal down")
        self.started.append({"args": args, **kwargs})


@pytest_asyncio.fixture
async def fake_temporal(app: FastAPI) -> AsyncIterator[FakeTemporal]:
    fake = FakeTemporal()

    async def _factory() -> FakeTemporal:
        return fake

    app.dependency_overrides[apply_router.temporal_client_factory] = lambda: _factory
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(apply_router.temporal_client_factory, None)


_VALID_TABS: dict[str, dict[str, Any]] = {
    "you": {
        "first_name": "Tina",
        "last_name": "Tampa",
        "cell_phone": "(813) 555-0142",
        "dob": "1988-04-12",
        "ssn": "123-45-6789",
        "marital_status": "unmarried",
        "dependents_count": 0,
        "current_address": {
            "street": "22 River Rd",
            "city": "Lakeland",
            "state": "fl",
            "zip": "33801",
        },
        "housing_status": "rent",
        "residence_years": 3,
        "residence_months": 2,
        "prior_address": None,
        "has_co_borrower": False,
        "co_borrower": None,
    },
    "property": {
        "occupancy": "str",
        "has_property": False,
        "address": None,
        "buy_box_states": ["FL"],
        "buy_box_metros": ["Tampa"],
        "target_price": "400000",
        "down_payment_pct": "0.25",
    },
    "income": {
        "employer_name": None,
        "years_employed": None,
        "monthly_income": None,
        "monthly_debts": "450",
        "liquid_assets": "180000",
    },
    "consent": {
        "soft_pull_authorized": True,
        "contact_consent": True,
        "terms_accepted": True,
        "typed_name": "tina  TAMPA",
    },
}


@pytest.fixture
def valid_tabs() -> Callable[[], dict[str, dict[str, Any]]]:
    return lambda: copy.deepcopy(_VALID_TABS)
