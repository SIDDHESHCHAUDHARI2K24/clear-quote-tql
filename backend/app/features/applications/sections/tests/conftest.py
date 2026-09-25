"""Fixtures for the verification-tab API tests (CQ-028a).

- `make_app`: builds a staff-owned application the same way production does:
  `users -> clients -> applications -> properties` plus a seeded
  `provider_los_records` / `provider_credit_reports` pair, then runs the
  real `import_from_los` and `run_and_persist`, so parties, housing,
  employment, liabilities, assets, FICO and flags are all real.
- `fake_temporal` (autouse): overrides `get_temporal_provider` with an
  in-memory fake that records signals/starts. The Temporal integration test
  (`test_resume_pipeline.py`) overrides it again with a real time-skipping
  environment.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from app.core.enums import ApplicationStatus, Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import (
    Property,
    PropertyAddressStatus,
    PropertyType,
)
from app.features.applications.sections.reverify import get_temporal_provider
from app.features.applications.service import import_from_los
from app.features.applications.verification.service import run_and_persist
from app.features.auth.models import User
from app.features.clients.models import Client as ClientModel
from app.integrations.credit.models import CreditPullType, ProviderCreditReport
from app.integrations.los.models import ProviderLosRecord
from conftest import StaffSession

_OCCUPANCY_LOS = {
    Occupancy.PRIMARY: "Primary_Residence",
    Occupancy.INVESTMENT: "Investment_Property",
}


@dataclass
class FakeHandle:
    temporal: FakeTemporal
    workflow_id: str

    async def describe(self) -> Any:
        if self.workflow_id not in self.temporal.running:
            raise RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")

        @dataclass
        class _Description:
            status: WorkflowExecutionStatus = WorkflowExecutionStatus.RUNNING

        return _Description()

    async def signal(self, _signal: Any) -> None:
        self.temporal.signals.append(self.workflow_id)


@dataclass
class FakeTemporal:
    running: set[str] = field(default_factory=set)
    signals: list[str] = field(default_factory=list)
    starts: list[str] = field(default_factory=list)

    def get_workflow_handle(self, workflow_id: str) -> FakeHandle:
        return FakeHandle(self, workflow_id)

    async def start_workflow(self, *_args: Any, id: str, **_kwargs: Any) -> None:  # noqa: A002
        self.starts.append(id)
        self.running.add(id)


@pytest_asyncio.fixture(autouse=True)
async def fake_temporal(app: FastAPI) -> AsyncIterator[FakeTemporal]:
    fake = FakeTemporal()

    async def _client() -> Any:
        return fake

    async def _provider() -> Any:
        return _client

    app.dependency_overrides[get_temporal_provider] = _provider
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_temporal_provider, None)


@pytest_asyncio.fixture
async def staff(make_staff_session: Callable[..., Awaitable[StaffSession]]) -> StaffSession:
    return await make_staff_session(role=UserRole.LO)


@pytest_asyncio.fixture
async def make_app(
    db_session: AsyncSession, staff: StaffSession
) -> Callable[..., Awaitable[Application]]:
    async def _make(
        *,
        occupancy: Occupancy | None = Occupancy.PRIMARY,
        strategy: Strategy | None = None,
        lo: User | None = None,
        housing: list[tuple[int, int]] | None = None,
        cell_phone: str | None = "2605551234",
        home_phone: str | None = None,
        ssn: str = "123456789",
        co_borrower: bool = False,
        monthly_income: str | None = "9000.00",
        liabilities: list[tuple[str, str]] | None = None,
        assets: str = "80000.00",
        address_status: PropertyAddressStatus = PropertyAddressStatus.SPECIFIC_ADDRESS,
        state: str = "IN",
        zip_code: str = "46802",
        status: ApplicationStatus | None = None,
        fico: int = 740,
    ) -> Application:
        owner = lo or staff.user
        client_row = ClientModel(
            full_name="Test Borrower",
            email=f"borrower-{uuid.uuid4()}@clearquote-demo.test",
            assigned_lo_id=owner.id,
        )
        db_session.add(client_row)
        await db_session.flush()

        loan_number = f"LOS-{uuid.uuid4().hex[:10]}"
        application = Application(
            client_id=client_row.id,
            lo_id=owner.id,
            strategy=strategy,
            requested_price=Decimal("300000.00"),
            status=ApplicationStatus.INTAKE,
            los_loan_guid=loan_number,
        )
        db_session.add(application)
        await db_session.flush()
        db_session.add(
            Property(
                application_id=application.id,
                address_status=address_status,
                street_address=(
                    "10 Subject St"
                    if address_status is PropertyAddressStatus.SPECIFIC_ADDRESS
                    else None
                ),
                city="Fort Wayne",
                state=state,
                county="Allen",
                zip=zip_code,
                property_type=PropertyType.SINGLE_FAMILY,
                number_of_units=1,
                recommend_matches=address_status is PropertyAddressStatus.TBD,
                buy_box_states=[state] if address_status is PropertyAddressStatus.TBD else [],
            )
        )

        rows = housing or [(3, 0)]
        payload: dict[str, Any] = {
            "borrower_first_name": "Test",
            "borrower_last_name": "Borrower",
            "borrower_ssn": ssn,
            "borrower_dob": "1985-01-01",
            "borrower_email": client_row.email,
            "borrower_cell_phone": cell_phone,
            "borrower_home_phone": home_phone,
            "has_co_borrower": co_borrower,
            "co_borrower_full_name": "Co Borrower" if co_borrower else None,
            "co_borrower_ssn": "987654321" if co_borrower else None,
            "co_borrower_dob": "1986-02-02" if co_borrower else None,
            "current_street_address": "1 Main St",
            "current_city": "Fort Wayne",
            "current_state": "IN",
            "current_zip": "46802",
            "current_housing_status": "Rent",
            "current_residence_years": rows[0][0],
            "current_residence_months": rows[0][1],
            "occupancy_type": _OCCUPANCY_LOS[occupancy] if occupancy is not None else None,
            "employment": (
                [{"employer_name": "Acme", "monthly_income": monthly_income}]
                if monthly_income is not None
                else []
            ),
            "liabilities": [
                {
                    "creditor_name": name,
                    "account_type": "Auto Loan",
                    "monthly_payment": payment,
                    "balance": "5000.00",
                }
                for name, payment in (liabilities or [("Wells Fargo", "300.00")])
            ],
            "assets": [{"account_type": "Checking", "verified_amount": assets}],
        }
        if len(rows) > 1:
            payload["previous_street_address"] = "2 Prior St"
            payload["previous_residence_years"] = rows[1][0]
        db_session.add(ProviderLosRecord(loan_number=loan_number, payload=payload))
        db_session.add(
            ProviderCreditReport(
                loan_number=loan_number,
                pull_type=CreditPullType.SOFT_PULL,
                experian_score=fico,
                equifax_score=None,
                transunion_score=None,
                middle_score=fico,
                tradelines=[],
            )
        )
        await db_session.commit()

        await import_from_los(application.id, db_session)
        await run_and_persist(application.id, db_session)
        if status is not None:
            application.status = status
            await db_session.commit()
        return application

    return _make
