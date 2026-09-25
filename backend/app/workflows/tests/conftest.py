"""Shared fixtures for `backend/app/workflows/tests/`.

- `bind_activities_to_test_session` (autouse): monkeypatches `app.workflows.
  db.session_factory` so every activity opens sessions bound to *this
  test's* already-open `db_session` connection (via savepoints), so
  activity writes are visible to test assertions and roll back with the
  rest of `db_session`'s isolation (plan.md #12).
- `install_fake_import_from_los` (autouse): CQ-010's `applications.service.
  import_from_los` isn't merged into this branch yet (plan.md #3) — installs
  a working stand-in (it just flips status; the persona fixtures below
  already write every row the real import would) into `sys.modules` if the
  real module isn't importable yet. Self-healing once CQ-010 merges: the
  helper detects the real module and monkeypatches its `import_from_los`
  attribute instead, so no test code needs to change.
- `temporal_env` / `temporal_worker` (session-scoped): a time-skipping
  `WorkflowEnvironment` plus the *real* `app.workflows.worker.build_worker`
  worker — so every workflow test exercises the actual production
  registration path, not a re-implementation.
- `make_persona_application`: builds the full row graph (User -> Client ->
  Application [-> Property, ApplicationParty, HousingHistory, Employment,
  Liability, Asset, a pre-seeded `representative_fico` field_value]) a
  persona test needs, independent of `seed/` (spec.md: CQ-011 does not
  depend on CQ-010).
- `seed_tax_rate` / `seed_conventional_curve` / `seed_dscr_curve_all_buckets`
  / `seed_market_rent` / `seed_str_revenue`: mock-provider fixture rows so
  `enrich_application`/`auto_price_application` succeed for real.
- `wait_for_status`: polls `applications.status` — used for personas that
  park at `needs_attention` (the workflow itself never returns for those;
  only `priced` is a completing `run()` return per spec.md).
"""

from __future__ import annotations

import asyncio
import sys
import types
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.core.enums import ApplicationStatus, FieldSource, Occupancy, Strategy, UserRole
from app.features.applications.assets.models import Asset, Employment
from app.features.applications.credit.models import Liability
from app.features.applications.housing.models import HousingHistory, HousingStatus
from app.features.applications.models import Application, ApplicationParty, PartyRole
from app.features.applications.property.models import Property, PropertyAddressStatus, PropertyType
from app.features.applications.verification.models import FieldValue
from app.features.auth.models import User
from app.features.clients.models import Client as ClientModel
from app.integrations.pricing.models import ProviderRateSheet, RateSheetProgram
from app.integrations.rent.models import ProviderRent
from app.integrations.str.models import ProviderStrRevenue
from app.integrations.tax.models import ProviderTaxRate
from app.workflows import db as workflow_db
from app.workflows import worker as worker_module

_IMPORT_SERVICE_MODULE = "app.features.applications.service"


@dataclass
class FakeImportResult:
    """Mirrors CQ-010's real `ImportResult` shape closely enough for
    `activities._dataclass_payload` — the persona fixtures below already
    write every child row the real `import_from_los` would."""

    application_id: uuid.UUID
    parties_created: int = 0
    housing_rows_created: int = 0
    employment_rows_created: int = 0
    liabilities_created: int = 0
    assets_created: int = 0


async def _fake_import_from_los(application_id: uuid.UUID, db: AsyncSession) -> FakeImportResult:
    application = await db.get(Application, application_id)
    if application is None:
        raise ValueError(f"No application with id {application_id}")
    application.status = ApplicationStatus.VERIFYING
    await db.flush()
    await db.commit()
    return FakeImportResult(application_id=application_id)


def install_import_from_los(
    monkeypatch: pytest.MonkeyPatch,
    fn: Callable[[uuid.UUID, AsyncSession], Awaitable[object]],
) -> None:
    """Installs `fn` as `app.features.applications.service.import_from_los`
    for the calling test (plan.md #3) — self-healing whether or not CQ-010
    has merged the real module yet. Tests call this directly (after the
    autouse default below already ran) to install a spy/failing variant."""
    if _IMPORT_SERVICE_MODULE not in sys.modules:
        monkeypatch.setitem(
            sys.modules, _IMPORT_SERVICE_MODULE, types.ModuleType(_IMPORT_SERVICE_MODULE)
        )
    module = sys.modules[_IMPORT_SERVICE_MODULE]
    monkeypatch.setattr(module, "import_from_los", fn, raising=False)


@pytest.fixture(autouse=True)
def install_fake_import_from_los(monkeypatch: pytest.MonkeyPatch) -> None:
    install_import_from_los(monkeypatch, _fake_import_from_los)


@pytest_asyncio.fixture
async def activities_session_factory(
    db_session: AsyncSession,
) -> Callable[[], AsyncSession]:
    conn = db_session.bind

    def _factory() -> AsyncSession:
        return AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    return _factory


@pytest_asyncio.fixture(autouse=True)
async def bind_activities_to_test_session(
    monkeypatch: pytest.MonkeyPatch,
    activities_session_factory: Callable[[], AsyncSession],
) -> None:
    monkeypatch.setattr(workflow_db, "session_factory", activities_session_factory)


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
) -> ApplicationStatus:
    """Polls `applications.status` via a Core column select (bypasses the
    ORM identity map, so it always sees the latest committed value from
    sibling activity sessions on the same connection) until it lands in
    `expected`. Needed for personas that park at `needs_attention` — the
    workflow's `run()` never returns for those (spec.md "Resume
    mechanics")."""

    async def _poll() -> ApplicationStatus:
        while True:
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
def wait_for_status() -> Callable[..., Awaitable[ApplicationStatus]]:
    """Injectable fixture wrapper around `_wait_for_status` — tests take
    this as a fixture parameter and call it with `(db_session,
    application_id, expected_statuses)`."""
    return _wait_for_status


@pytest_asyncio.fixture
async def make_persona_application(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[Application]]:
    async def _make(
        *,
        occupancy: Occupancy = Occupancy.PRIMARY,
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
        representative_fico: Decimal | None = Decimal("740"),
    ) -> Application:
        """Builds the full row graph one persona needs, independent of
        `seed/` (spec.md). `housing_rows` defaults to a single 36-month
        current residence (comfortably passes `housing_history_24mo`);
        pass e.g. `[(1, 2)]` for Ben Ford's 14-month defect. A
        `representative_fico` field_value is pre-seeded because no activity
        in this six-stage pipeline ever writes it (a real credit pull is
        out of scope, plan.md #11)."""
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

        application = Application(
            client_id=client.id,
            lo_id=lo.id,
            occupancy=occupancy,
            strategy=strategy,
            requested_price=requested_price,
            status=ApplicationStatus.INTAKE,
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

        if borrower_ssn is not None or borrower_dob is not None:
            db_session.add(
                ApplicationParty(
                    application_id=application.id,
                    role=PartyRole.BORROWER,
                    first_name="Test",
                    last_name="Borrower",
                    cell_phone=borrower_cell_phone,
                    ssn_encrypted=borrower_ssn,
                    dob=borrower_dob,
                )
            )

        for sequence, (years, months) in enumerate(housing_rows or [(3, 0)]):
            db_session.add(
                HousingHistory(
                    application_id=application.id,
                    sequence=sequence,
                    street_address="1 Main St",
                    city="Fort Wayne",
                    state=state,
                    zip=zip_code,
                    housing_status=HousingStatus.RENT,
                    residence_years=years,
                    residence_months=months,
                )
            )

        if monthly_income is not None:
            db_session.add(
                Employment(
                    application_id=application.id,
                    employer_name="Test Employer",
                    monthly_income=monthly_income,
                    years_at_job=Decimal("3.0"),
                )
            )

        if liability_payment is not None:
            db_session.add(
                Liability(
                    application_id=application.id,
                    creditor_name="Test Creditor",
                    account_type="credit_card",
                    monthly_payment=liability_payment,
                    balance=liability_payment * 10,
                )
            )

        if assets_amount is not None:
            db_session.add(
                Asset(
                    application_id=application.id,
                    account_type="checking",
                    institution="Test Bank",
                    verified_amount=assets_amount,
                )
            )

        if representative_fico is not None:
            db_session.add(
                FieldValue(
                    application_id=application.id,
                    field_key="representative_fico",
                    value=str(representative_fico),
                    source=FieldSource.CREDIT_BUREAU,
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
