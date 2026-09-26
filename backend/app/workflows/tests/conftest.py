"""Shared fixtures for `backend/app/workflows/tests/`.

- `bind_activities_to_test_session` (autouse): monkeypatches `app.workflows.
  db.session_factory` so every activity opens sessions bound to *this
  test's* already-open `db_session` connection (via savepoints), so
  activity writes are visible to test assertions and roll back with the
  rest of `db_session`'s isolation (plan.md #12).
- `install_import_from_los`: CQ-010 has merged (plan.md #13) — by default
  every workflow test now exercises the *real* `app.features.applications.
  service.import_from_los` via `make_persona_application`'s seeded
  `ProviderLosRecord`/`ProviderCreditReport` rows. Tests that need a spy or
  a failing double (AC2/AC3's thin-wrapper/retry tests) call this helper to
  monkeypatch both the service module's attribute and `app.workflows.
  activities`'s own already-bound name (activities.py imports the function
  at module scope, so patching only the service module wouldn't reach it).
- `temporal_env` (session-scoped): a time-skipping `WorkflowEnvironment`.
  `temporal_worker` (per test): the *real* `app.workflows.worker.
  build_worker` worker — so every workflow test exercises the actual
  production registration path, not a re-implementation.
- Isolation (the asyncpg "another operation is in progress" flake):
  `db_lock` serialises activity sessions and `wait_for_status` polls on
  the one shared connection; the per-test worker drains (holding the lock)
  before `db_session` rolls back; `terminate_started_workflows` terminates
  whatever a test left running; `bound_default_retries` caps
  `DEFAULT_RETRY_POLICY` at two attempts in tests.
- `make_persona_application`: builds the row graph a persona test needs
  (User -> Client -> Application [-> Property] plus a seeded
  `ProviderLosRecord`/`ProviderCreditReport` pair), independent of `seed/`
  (spec.md: CQ-011 does not depend on CQ-010). `application_parties`,
  `housing_history`, `employment`, `liabilities`, `assets` and
  `field_values.representative_fico` are written by the real
  `import_application` activity when the workflow runs, exactly as they
  would be in production — not pre-seeded here, to avoid duplicating rows
  the real import also writes.
- `seed_tax_rate` / `seed_conventional_curve` / `seed_dscr_curve_all_buckets`
  / `seed_market_rent` / `seed_str_revenue`: mock-provider fixture rows so
  `enrich_application`/`auto_price_application` succeed for real.
- `wait_for_status`: polls `applications.status` — used for personas that
  park at `needs_attention` (the workflow itself never returns for those;
  only `priced` is a completing `run()` return per spec.md).
"""

from __future__ import annotations

import asyncio
import functools
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import (
    Client,
    Interceptor,
    OutboundInterceptor,
    StartWorkflowInput,
    WorkflowHandle,
)
from temporalio.common import RetryPolicy
from temporalio.service import RPCError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.core.enums import ApplicationStatus, Occupancy, Strategy, UserRole
from app.features.applications.models import Application
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.auth.models import User
from app.features.clients.models import Client as ClientModel
from app.integrations.credit.models import CreditPullType, ProviderCreditReport
from app.integrations.los.models import ProviderLosRecord
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram
from app.integrations.rent.models import ProviderRent
from app.integrations.str.models import ProviderStrRevenue
from app.integrations.tax.models import ProviderTaxRate
from app.workflows import activities as activities_module
from app.workflows import application_pipeline, retry_policies
from app.workflows import db as workflow_db
from app.workflows import worker as worker_module
from app.workflows.retry_policies import NON_RETRYABLE_ERROR_TYPES

_IMPORT_SERVICE_MODULE = "app.features.applications.service"

_OCCUPANCY_TO_LOS_STRING: dict[Occupancy, str] = {
    Occupancy.PRIMARY: "Primary_Residence",
    Occupancy.INVESTMENT: "Investment_Property",
}


@dataclass
class FakeImportResult:
    """A stand-in `ImportResult`-shaped return value for spy tests (AC2's
    `test_import_application_is_a_thin_wrapper`) — doesn't need to be a real
    `ImportResult` since those tests only assert identity/pass-through, not
    field values."""

    application_id: uuid.UUID
    parties_created: int = 0
    housing_rows_created: int = 0
    employment_rows_created: int = 0
    liabilities_created: int = 0
    assets_created: int = 0


def install_import_from_los(
    monkeypatch: pytest.MonkeyPatch,
    fn: Callable[[uuid.UUID, AsyncSession], Awaitable[object]],
) -> None:
    """Installs `fn` in place of `import_from_los` for the calling test
    (plan.md #13, supersedes #3 now that CQ-010's real module is merged).
    Patches `app.workflows.activities.import_from_los` (the name
    `import_application` actually calls, bound at module-import time) and,
    for good measure, the service module's own attribute too."""
    monkeypatch.setattr(activities_module, "import_from_los", fn)
    module = sys.modules.get(_IMPORT_SERVICE_MODULE)
    if module is not None:
        monkeypatch.setattr(module, "import_from_los", fn, raising=False)


@pytest.fixture
def db_lock() -> asyncio.Lock:
    """One lock per test serialising every use of the test's single
    `db_session` connection. Activity sessions (below) and test-side
    polling (`wait_for_status`) take it, so two asyncpg operations never
    overlap on the connection ("another operation is in progress")."""
    return asyncio.Lock()


@pytest_asyncio.fixture
async def activities_session_factory(
    db_session: AsyncSession, db_lock: asyncio.Lock
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Every activity session is a savepoint session on `db_session`'s
    connection, opened and closed while holding `db_lock`. Production
    activities only ever use `async with session_factory() as db:`, so an
    async context manager is a drop-in replacement for `AsyncSessionLocal`."""
    conn = db_session.bind

    @asynccontextmanager
    async def _factory() -> AsyncIterator[AsyncSession]:
        async with db_lock:
            session = AsyncSession(
                bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            try:
                yield session
            finally:
                await session.close()

    return _factory


@pytest_asyncio.fixture(autouse=True)
async def bind_activities_to_test_session(
    monkeypatch: pytest.MonkeyPatch,
    activities_session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> None:
    monkeypatch.setattr(workflow_db, "session_factory", activities_session_factory)


# Test-only bound on retries: `DEFAULT_RETRY_POLICY` is unlimited in
# production, which let a failing activity retry forever (time-skipping
# makes that fast) and leak into later tests.
TEST_DEFAULT_RETRY_POLICY = RetryPolicy(
    maximum_attempts=2, non_retryable_error_types=NON_RETRYABLE_ERROR_TYPES
)


@pytest.fixture(autouse=True)
def bound_default_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Workflow modules read `DEFAULT_RETRY_POLICY` from the (passed-through)
    `retry_policies` module when the sandbox re-imports them per run, so
    patching the module attribute reaches every new workflow run."""
    monkeypatch.setattr(retry_policies, "DEFAULT_RETRY_POLICY", TEST_DEFAULT_RETRY_POLICY)
    monkeypatch.setattr(application_pipeline, "DEFAULT_RETRY_POLICY", TEST_DEFAULT_RETRY_POLICY)


class _StartedWorkflows(Interceptor):
    """Client interceptor recording every workflow id started through
    `temporal_client`, so teardown can terminate what a test left running
    (the time-skipping server has no ListWorkflowExecutions)."""

    def __init__(self) -> None:
        self.ids: list[str] = []

    def intercept_client(self, next: OutboundInterceptor) -> OutboundInterceptor:
        return _RecordStarts(next, self)


class _RecordStarts(OutboundInterceptor):
    def __init__(self, next: OutboundInterceptor, tracker: _StartedWorkflows) -> None:
        super().__init__(next)
        self._tracker = tracker

    async def start_workflow(self, input: StartWorkflowInput) -> WorkflowHandle[Any, Any]:
        handle = await super().start_workflow(input)
        self._tracker.ids.append(input.id)
        return handle


@pytest_asyncio.fixture(scope="session")
async def temporal_env() -> AsyncIterator[WorkflowEnvironment]:
    env = await WorkflowEnvironment.start_time_skipping()
    yield env
    await env.shutdown()


@pytest.fixture(scope="session")
def started_workflows() -> _StartedWorkflows:
    return _StartedWorkflows()


@pytest_asyncio.fixture(scope="session")
async def temporal_client(
    temporal_env: WorkflowEnvironment, started_workflows: _StartedWorkflows
) -> Client:
    config = temporal_env.client.config()
    config["interceptors"] = [*config["interceptors"], started_workflows]
    return Client(**config)


@pytest_asyncio.fixture(autouse=True)
async def terminate_started_workflows(
    temporal_client: Client, started_workflows: _StartedWorkflows
) -> AsyncIterator[None]:
    """Teardown: terminates every workflow this test started that is still
    running (e.g. a pipeline parked at `needs_attention`), so no later
    test's worker picks up its tasks. Autouse fixtures set up first and so
    tear down last: after every worker of this test has drained."""
    started_workflows.ids.clear()
    yield
    for workflow_id in started_workflows.ids:
        try:
            await temporal_client.get_workflow_handle(workflow_id).terminate(reason="test teardown")
        except RPCError:
            pass  # Already completed, failed or terminated.
    started_workflows.ids.clear()


@pytest_asyncio.fixture
async def temporal_worker(
    temporal_client: Client,
    bind_activities_to_test_session: None,
    db_lock: asyncio.Lock,
) -> AsyncIterator[Worker]:
    """The *real* `app.workflows.worker.build_worker` — every workflow test
    exercises the production registration path (AC6 has its own dedicated
    assertion too, but every other test incidentally proves the worker
    actually runs the real workflow + all its activities end to end).

    Scoped per test so it drains before `db_session` rolls back: it
    depends on the session binding (so pytest tears it down first), and
    shuts down while holding `db_lock`, so any activity still running is
    cancelled while waiting for the lock -- never mid-way through a
    database operation on the shared connection."""
    worker = worker_module.build_worker(temporal_client)
    async with worker:
        yield worker
        await db_lock.acquire()
    db_lock.release()


async def _wait_for_status(
    db_session: AsyncSession,
    application_id: uuid.UUID,
    expected: set[ApplicationStatus],
    timeout: float = 10.0,
    *,
    lock: asyncio.Lock | None = None,
) -> ApplicationStatus:
    """Polls `applications.status` via a Core column select (bypasses the
    ORM identity map, so it always sees the latest committed value from
    sibling activity sessions on the same connection) until it lands in
    `expected`. Needed for personas that park at `needs_attention` — the
    workflow's `run()` never returns for those (spec.md "Resume
    mechanics"). Each poll holds `lock` (the test's `db_lock`) so it never
    overlaps an activity's session on the shared connection."""
    guard: AbstractAsyncContextManager[object] = lock if lock is not None else nullcontext()

    async def _poll() -> ApplicationStatus:
        while True:
            async with guard:
                status = (
                    await db_session.execute(
                        select(Application.status).where(Application.id == application_id)
                    )
                ).scalar_one()
            if status in expected:
                return status
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(_poll(), timeout=timeout)


@pytest.fixture
def wait_for_status(db_lock: asyncio.Lock) -> Callable[..., Awaitable[ApplicationStatus]]:
    """Injectable fixture wrapper around `_wait_for_status`, bound to this
    test's `db_lock` — tests call it with `(db_session, application_id,
    expected_statuses)`."""
    return functools.partial(_wait_for_status, lock=db_lock)


@pytest_asyncio.fixture
async def make_persona_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(
        *,
        occupancy: Occupancy | None = Occupancy.PRIMARY,
        strategy: Strategy | None = None,
        requested_price: Decimal | None = Decimal("300000.00"),
        state: str = "IN",
        county: str = "Allen",
        zip_code: str = "46802",
        address_status: PropertyAddressStatus = PropertyAddressStatus.SPECIFIC_ADDRESS,
        property_type: PropertyType = PropertyType.SINGLE_FAMILY,
        number_of_units: int = 1,
        borrower_ssn: str | None = "123456789",
        borrower_dob: date | None = date(1985, 1, 1),
        borrower_cell_phone: str | None = "2605551234",
        housing_rows: list[tuple[int, int]] | None = None,
        monthly_income: Decimal | None = Decimal("9000.00"),
        liability_payment: Decimal | None = Decimal("300.00"),
        assets_amount: Decimal | None = Decimal("80000.00"),
        representative_fico: int | None = 740,
    ) -> Application:
        """Builds the row graph one persona needs, independent of `seed/`
        (spec.md), for the real `import_application` activity to import
        from: a `users`/`clients`/`applications`[/`properties`] row graph
        plus a matching `provider_los_records`/`provider_credit_reports`
        pair (same recipe as CQ-010's own `applications/tests/
        test_service.py`). `application_parties`, `housing_history`,
        `employment`, `liabilities`, `assets` and
        `field_values.representative_fico` are deliberately NOT written
        here — the real `import_from_los` writes them from the seeded LOS
        payload/credit report when the workflow's `import_application`
        activity runs (plan.md #13 follow-up (2)), so pre-seeding them here
        would create duplicate rows.

        `occupancy=None` reproduces persona 7 (Aisha Coleman)'s defect for
        real: the LOS payload's `occupancy_type` is left unset, so
        `import_from_los` leaves `applications.occupancy` `NULL` exactly as
        it would for a real LOS record missing that field.

        `housing_rows` defaults to a single 36-month current residence
        (comfortably passes `housing_history_24mo`); pass e.g. `[(1, 2)]`
        for Ben Ford's 14-month, no-prior-address defect.
        """
        lo = User(
            email=f"lo-{uuid.uuid4()}@clearquote-demo.test",
            password_hash="not-a-real-hash",
            role=UserRole.LO,
            full_name="Test LO",
        )
        db_session.add(lo)
        await db_session.flush()

        client = ClientModel(
            full_name="Test Client",
            email=f"client-{uuid.uuid4()}@clearquote-demo.test",
            assigned_lo_id=lo.id,
        )
        db_session.add(client)
        await db_session.flush()

        loan_number = f"LOS-{uuid.uuid4().hex[:10]}"
        application = Application(
            client_id=client.id,
            lo_id=lo.id,
            occupancy=None,  # set for real by import_from_los, below.
            strategy=strategy,
            requested_price=requested_price,
            status=ApplicationStatus.INTAKE,
            los_loan_guid=loan_number,
        )
        db_session.add(application)
        await db_session.flush()

        db_session.add(
            Property(
                application_id=application.id,
                address_status=address_status,
                state=state,
                county=county,
                zip=zip_code,
                property_type=property_type,
                number_of_units=number_of_units,
            )
        )

        rows = housing_rows or [(3, 0)]
        current_years, current_months = rows[0]
        previous_row = rows[1] if len(rows) > 1 else None

        payload: dict[str, object] = {
            "borrower_first_name": "Test",
            "borrower_last_name": "Borrower",
            "borrower_full_name": "Test Borrower",
            "borrower_ssn": borrower_ssn,
            "borrower_dob": borrower_dob.isoformat() if borrower_dob is not None else None,
            "borrower_cell_phone": borrower_cell_phone,
            "has_co_borrower": False,
            "current_street_address": "1 Main St",
            "current_city": "Fort Wayne",
            "current_state": state,
            "current_zip": zip_code,
            "current_housing_status": "Rent",
            "current_residence_years": current_years,
            "current_residence_months": current_months,
            "occupancy_type": (
                _OCCUPANCY_TO_LOS_STRING[occupancy] if occupancy is not None else None
            ),
        }
        if previous_row is not None:
            payload["previous_street_address"] = "2 Prior St"
            payload["previous_residence_years"] = previous_row[0]

        if monthly_income is not None:
            payload["employment"] = [
                {
                    "employer_name": "Test Employer",
                    "monthly_income": str(monthly_income),
                    "years_at_job": "3.0",
                    "self_employed": False,
                }
            ]
        if liability_payment is not None:
            payload["liabilities"] = [
                {
                    "creditor_name": "Test Creditor",
                    "account_type": "credit_card",
                    "monthly_payment": str(liability_payment),
                    "balance": str(liability_payment * 10),
                }
            ]
        if assets_amount is not None:
            payload["assets"] = [
                {
                    "account_type": "checking",
                    "institution": "Test Bank",
                    "verified_amount": str(assets_amount),
                }
            ]

        db_session.add(ProviderLosRecord(loan_number=loan_number, payload=payload))

        if representative_fico is not None:
            db_session.add(
                ProviderCreditReport(
                    loan_number=loan_number,
                    pull_type=CreditPullType.SOFT_PULL,
                    experian_score=representative_fico,
                    equifax_score=None,
                    transunion_score=None,
                    middle_score=representative_fico,
                    tradelines=[],
                )
            )

        await db_session.flush()
        await db_session.commit()
        return application

    return _make


@pytest_asyncio.fixture
async def seed_tax_rate(db_session: AsyncSession) -> Callable[..., Awaitable[None]]:
    async def _seed(
        state: str = "IN", county: str = "Allen", annual_rate_pct: Decimal = Decimal("1.0000")
    ) -> None:
        db_session.add(
            ProviderTaxRate(
                state=state,
                county=county,
                annual_rate_pct=annual_rate_pct,
                source_name="SmartAsset",
                as_of=date.today(),
            )
        )
        await db_session.commit()

    return _seed


@pytest_asyncio.fixture
async def seed_conventional_curve(db_session: AsyncSession) -> Callable[..., Awaitable[None]]:
    """A single Conventional 30yr rate curve — matches `pricing/scenarios/
    tests/test_default_scenarios_primary.py`'s fixture recipe."""

    async def _seed(par_rate: Decimal = Decimal("7.000")) -> None:
        offsets = [
            Decimal("-0.250"),
            Decimal("-0.125"),
            Decimal("0.000"),
            Decimal("0.125"),
            Decimal("0.250"),
        ]
        for index, offset in enumerate(offsets):
            db_session.add(
                ProviderRateSheet(
                    investor_name=f"Investor Conv {index}",
                    product_name="Conventional 30 Yr Fixed",
                    program=RateSheetProgram.CONVENTIONAL,
                    base_rate=par_rate + offset,
                    base_price=Decimal("100.000") - offset * Decimal("4"),
                    min_fico=680,
                    max_ltv=Decimal("97.00"),
                    lock_days=30,
                    active=True,
                )
            )
        await db_session.commit()

    return _seed


@pytest_asyncio.fixture
async def seed_dscr_curve_all_buckets(db_session: AsyncSession) -> Callable[..., Awaitable[None]]:
    """Seeds the SAME DSCR curve for all three `DSCRBucket` values, so
    `create_default_scenarios`'s two-pass loop succeeds on either pass
    regardless of which bucket it actually converges to — persona tests
    only need auto-pricing to *succeed*, not a specific group count."""

    async def _seed(par_rate: Decimal = Decimal("7.500")) -> None:
        offsets = [
            Decimal("-0.250"),
            Decimal("-0.125"),
            Decimal("0.000"),
            Decimal("0.125"),
            Decimal("0.250"),
        ]
        for bucket in ("BELOW_1_00", "ONE_TO_1_25", "GE_1_25"):
            for index, offset in enumerate(offsets):
                db_session.add(
                    ProviderRateSheet(
                        investor_name=f"Investor {bucket}-{index}",
                        product_name="DSCR 30 Yr Fixed",
                        program=RateSheetProgram.DSCR,
                        base_rate=par_rate + offset,
                        base_price=Decimal("100.000") - offset * Decimal("4"),
                        min_fico=680,
                        max_ltv=Decimal("80.00"),
                        dscr_bucket=bucket,
                        lock_days=30,
                        active=True,
                    )
                )
        await db_session.commit()

    return _seed


@pytest_asyncio.fixture
async def seed_market_rent(db_session: AsyncSession) -> Callable[..., Awaitable[None]]:
    async def _seed(
        zip_code: str = "46802", beds: int = 1, market_rent: Decimal = Decimal("2440.00")
    ) -> None:
        db_session.add(
            ProviderRent(
                zip=zip_code,
                beds=beds,
                market_rent=market_rent,
                rent_low=market_rent * Decimal("0.9"),
                rent_high=market_rent * Decimal("1.1"),
                comps_count=5,
                as_of=date.today(),
            )
        )
        await db_session.commit()

    return _seed


@pytest_asyncio.fixture
async def seed_str_revenue(db_session: AsyncSession) -> Callable[..., Awaitable[None]]:
    async def _seed(
        zip_code: str = "28803", beds: int = 1, annual_revenue: Decimal = Decimal("36600.00")
    ) -> None:
        db_session.add(
            ProviderStrRevenue(
                zip=zip_code,
                beds=beds,
                annual_revenue=annual_revenue,
                occupancy_pct=Decimal("65.00"),
                adr=Decimal("150.00"),
                comps_count=5,
                as_of=date.today(),
            )
        )
        await db_session.commit()

    return _seed
