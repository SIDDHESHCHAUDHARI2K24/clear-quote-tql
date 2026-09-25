"""Shared fixtures for `backend/app/workflows/tests/`.

- `bind_activities_to_test_session` (autouse): monkeypatches `app.workflows.
  db.session_factory` so every activity opens sessions bound to *this
  test's* already-open `db_session` connection (via savepoints), so
  activity writes are visible to test assertions and roll back with the
  rest of `db_session`'s isolation (plan.md #12). Its teardown waits for
  every activity session to close before `db_session` rolls back.
- `activity_session_gate`: an `ActivitySessionGate` that keeps the test's
  own queries and in-flight activity sessions from overlapping on that one
  shared connection (docs/backlog/p34-test-flake-fix.md). `wait_for_status`
  already uses it; query `db_session` inside `gate.test_turn()` if a
  workflow may still be running.
- `install_import_from_los`: CQ-010 has merged (plan.md #13) — by default
  every workflow test now exercises the *real* `app.features.applications.
  service.import_from_los` via `make_persona_application`'s seeded
  `ProviderLosRecord`/`ProviderCreditReport` rows. Tests that need a spy or
  a failing double (AC2/AC3's thin-wrapper/retry tests) call this helper to
  monkeypatch both the service module's attribute and `app.workflows.
  activities`'s own already-bound name (activities.py imports the function
  at module scope, so patching only the service module wouldn't reach it).
- `temporal_env` / `temporal_worker` (session-scoped): a time-skipping
  `WorkflowEnvironment` plus the *real* `app.workflows.worker.build_worker`
  worker — so every workflow test exercises the actual production
  registration path, not a re-implementation.
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
import contextlib
import functools
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
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
from app.workflows import db as workflow_db
from app.workflows import worker as worker_module

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


class ActivitySessionGate:
    """Serializes the test's own queries against in-flight activity
    sessions on the one shared `db_session` connection
    (docs/backlog/p34-test-flake-fix.md).

    Activities run in the worker on the test's event loop, bound to the
    test's connection. Without this, a test could (a) see a status an
    activity had only *flushed* and assert/tear down while that activity
    was still writing -- asyncpg "another operation is in progress" on the
    teardown rollback, then a poisoned pooled connection for every later
    test -- or (b) open its own savepoint inside an activity's savepoint,
    which the activity's RELEASE then destroys ("savepoint ... does not
    exist").

    - Activity sessions (see `activities_session_factory`) count as in
      flight from `__aenter__` to `__aexit__`, and wait while a test turn
      is running.
    - `test_turn()` waits until no activity session is open, and blocks new
      ones until it exits. `wait_for_status` polls inside it; a test that
      queries `db_session` while a workflow may still be running should do
      the same.
    - `wait_idle()` is the teardown guard in `bind_activities_to_test_
      session`. `close()` runs right after it drains, so an activity that
      somehow starts after teardown (instead of merely still running at
      teardown) fails loudly instead of touching a connection `db_session`
      has already rolled back.
    """

    def __init__(self) -> None:
        self._cond = asyncio.Condition()
        self._in_flight = 0
        self._test_turn = False
        self._closed = False

    @property
    def in_flight(self) -> int:
        return self._in_flight

    async def enter_activity(self) -> None:
        async with self._cond:
            if self._closed:
                raise RuntimeError(
                    "activity started after test teardown -- a workflow from this "
                    "test is still running"
                )
            await self._cond.wait_for(lambda: not self._test_turn)
            self._in_flight += 1

    async def exit_activity(self) -> None:
        # Decrements synchronously (no `await` in between) so a cancellation
        # of the caller -- e.g. `_GatedActivitySession.__aexit__` racing a
        # workflow-level timeout -- can never leave `_in_flight` stuck above
        # its true value. Only the wake-up notification is awaited, and it
        # is shielded so a cancellation there still lets waiters (`wait_
        # idle`, `test_turn`) see the updated count instead of blocking
        # until their own timeout.
        self._in_flight -= 1
        await asyncio.shield(self._notify_in_flight_change())

    async def _notify_in_flight_change(self) -> None:
        async with self._cond:
            self._cond.notify_all()

    @contextlib.asynccontextmanager
    async def test_turn(self, timeout: float = 10.0) -> AsyncIterator[None]:
        async def _acquire() -> None:
            async with self._cond:
                await self._cond.wait_for(lambda: self._in_flight == 0 and not self._test_turn)
                self._test_turn = True

        try:
            await asyncio.wait_for(_acquire(), timeout=timeout)
        except TimeoutError:
            raise AssertionError(
                f"test_turn() timed out after {timeout}s waiting for "
                f"{self._in_flight} in-flight activity session(s) to close"
            ) from None
        try:
            yield
        finally:
            async with self._cond:
                self._test_turn = False
                self._cond.notify_all()

    async def wait_idle(self, timeout: float) -> None:
        async def _wait() -> None:
            async with self._cond:
                await self._cond.wait_for(lambda: self._in_flight == 0)

        await asyncio.wait_for(_wait(), timeout=timeout)

    async def close(self) -> None:
        """Closes the gate for good: any later `enter_activity()` raises
        instead of silently touching a connection `db_session` has already
        rolled back. Call only after `wait_idle()` has drained in-flight
        sessions."""
        async with self._cond:
            self._closed = True


class _GatedActivitySession(AsyncSession):
    """An `AsyncSession` that registers with an `ActivitySessionGate` for
    the span of its `async with` block (how every activity opens it)."""

    _gate: ActivitySessionGate

    async def __aenter__(self) -> _GatedActivitySession:
        await self._gate.enter_activity()
        return self

    async def __aexit__(self, type_: Any, value: Any, traceback: Any) -> None:
        try:
            await super().__aexit__(type_, value, traceback)
        finally:
            await self._gate.exit_activity()


@pytest_asyncio.fixture
async def activity_session_gate() -> ActivitySessionGate:
    return ActivitySessionGate()


@pytest_asyncio.fixture
async def activities_session_factory(
    db_session: AsyncSession,
    activity_session_gate: ActivitySessionGate,
) -> Callable[[], AsyncSession]:
    conn = db_session.bind

    def _factory() -> AsyncSession:
        session = _GatedActivitySession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        session._gate = activity_session_gate
        return session

    return _factory


# How long teardown waits for a still-running activity before failing the
# test that leaked it (instead of rolling back under it).
_ACTIVITY_DRAIN_TIMEOUT_S = 10.0


@pytest_asyncio.fixture(autouse=True)
async def bind_activities_to_test_session(
    monkeypatch: pytest.MonkeyPatch,
    activities_session_factory: Callable[[], AsyncSession],
    activity_session_gate: ActivitySessionGate,
) -> AsyncIterator[None]:
    monkeypatch.setattr(workflow_db, "session_factory", activities_session_factory)
    yield
    # Runs before `db_session`'s teardown (it depends on `db_session`), so
    # the outer rollback never races an activity still using the
    # connection.
    try:
        await activity_session_gate.wait_idle(_ACTIVITY_DRAIN_TIMEOUT_S)
    except TimeoutError:
        pytest.fail(
            f"{activity_session_gate.in_flight} activity session(s) still open on this "
            f"test's connection after {_ACTIVITY_DRAIN_TIMEOUT_S}s: wait for the workflow "
            "to reach a terminal state before the test ends"
        )
    finally:
        # Closes the gate even if `wait_idle` timed out and failed the test
        # above: any activity that starts *after* this point (rather than
        # merely still running at teardown, which `wait_idle` already
        # guards) must never touch a connection `db_session` is about to
        # roll back.
        await activity_session_gate.close()


@pytest_asyncio.fixture(scope="session")
async def temporal_env() -> AsyncIterator[WorkflowEnvironment]:
    env = await WorkflowEnvironment.start_time_skipping()
    yield env
    await env.shutdown()


@pytest_asyncio.fixture(scope="session")
async def temporal_client(temporal_env: WorkflowEnvironment) -> Client:
    return temporal_env.client


@pytest_asyncio.fixture(scope="session")
async def temporal_worker(temporal_client: Client) -> AsyncIterator[Worker]:
    """The *real* `app.workflows.worker.build_worker` — every workflow test
    exercises the production registration path (AC6 has its own dedicated
    assertion too, but every other test incidentally proves the worker
    actually runs the real workflow + all seven activities end to end)."""
    worker = worker_module.build_worker(temporal_client)
    async with worker:
        yield worker


async def _wait_for_status(
    db_session: AsyncSession,
    application_id: uuid.UUID,
    expected: set[ApplicationStatus],
    timeout: float = 10.0,
    gate: ActivitySessionGate | None = None,
) -> ApplicationStatus:
    """Polls `applications.status` via a Core column select (bypasses the
    ORM identity map, so it always sees the latest committed value from
    sibling activity sessions on the same connection) until it lands in
    `expected`. Needed for personas that park at `needs_attention` — the
    workflow's `run()` never returns for those (spec.md "Resume
    mechanics").

    With `gate` (the `wait_for_status` fixture always passes it), each poll
    runs only while no activity session is open, so a matching status means
    the activity that wrote it has finished all its writes, not just
    flushed the status (docs/backlog/p34-test-flake-fix.md)."""

    async def _read_status() -> ApplicationStatus:
        result = await db_session.execute(
            select(Application.status).where(Application.id == application_id)
        )
        return result.scalar_one()

    async def _poll() -> ApplicationStatus:
        while True:
            if gate is None:
                status = await _read_status()
            else:
                async with gate.test_turn():
                    status = await _read_status()
            if status in expected:
                return status
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(_poll(), timeout=timeout)


@pytest.fixture
def wait_for_status(
    activity_session_gate: ActivitySessionGate,
) -> Callable[..., Awaitable[ApplicationStatus]]:
    """Injectable fixture wrapper around `_wait_for_status` — tests take
    this as a fixture parameter and call it with `(db_session,
    application_id, expected_statuses)`."""
    return functools.partial(_wait_for_status, gate=activity_session_gate)


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
