"""AC6/AC7: `require_roles` role gate and `scope_applications` LO/Manager
scoping."""

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_staff, require_roles, scope_applications
from app.core.enums import Occupancy, UserRole
from app.core.errors import register_exception_handlers
from app.features.applications.models import Application
from app.features.auth.models import User
from app.features.clients.models import Client


def _fake_user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"fake-{uuid.uuid4()}@example.com",
        password_hash="x",
        role=role,
        full_name="Fake User",
    )


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/admin-only", dependencies=[Depends(require_roles(UserRole.ADMIN))])
    def _admin_only() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_require_roles() -> None:
    app = _build_test_app()
    client = TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides[get_current_staff] = lambda: _fake_user(UserRole.LO)
    lo_response = client.get("/admin-only")
    assert lo_response.status_code == 403
    assert lo_response.json()["error"]["code"] == "FORBIDDEN"

    app.dependency_overrides[get_current_staff] = lambda: _fake_user(UserRole.ADMIN)
    admin_response = client.get("/admin-only")
    assert admin_response.status_code == 200
    assert admin_response.json() == {"ok": True}


async def _make_staff(db_session: AsyncSession, role: UserRole) -> User:
    user = User(
        email=f"staff-{uuid.uuid4()}@example.com",
        password_hash="hashed",
        role=role,
        full_name="Test Staff",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_application(db_session: AsyncSession, lo: User) -> Application:
    client = Client(
        full_name="Test Client",
        email=f"client-{uuid.uuid4()}@example.com",
        assigned_lo_id=lo.id,
    )
    db_session.add(client)
    await db_session.flush()

    application = Application(client_id=client.id, lo_id=lo.id, occupancy=Occupancy.PRIMARY)
    db_session.add(application)
    await db_session.flush()
    return application


@pytest.fixture
async def _scoped_fixture(
    db_session: AsyncSession,
) -> tuple[User, User, User, Application, Application]:
    lo1 = await _make_staff(db_session, UserRole.LO)
    lo2 = await _make_staff(db_session, UserRole.LO)
    manager = await _make_staff(db_session, UserRole.MANAGER)

    app1 = await _make_application(db_session, lo1)
    app2 = await _make_application(db_session, lo2)
    return lo1, lo2, manager, app1, app2


async def test_scope_applications(
    db_session: AsyncSession,
    _scoped_fixture: tuple[User, User, User, Application, Application],
) -> None:
    lo1, lo2, manager, app1, app2 = _scoped_fixture

    async def _ids(stmt: Select[Application]) -> set[uuid.UUID]:
        result = await db_session.execute(stmt)
        return {row.id for row in result.scalars()}

    # An LO sees only their own applications, even when another LO's id is
    # passed as `lo_id` (Decision #11: the arg is ignored for an LO).
    assert await _ids(scope_applications(select(Application), lo1, lo_id=lo2.id)) == {app1.id}
    assert await _ids(scope_applications(select(Application), lo2)) == {app2.id}

    # A Manager sees all applications with no filter...
    assert await _ids(scope_applications(select(Application), manager)) == {app1.id, app2.id}

    # ...and only one LO's when `lo_id` is given.
    assert await _ids(scope_applications(select(Application), manager, lo_id=lo2.id)) == {app2.id}
