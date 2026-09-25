# CQ-004 Backend skeleton

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-003 |
| Kaneo task | CQ-004 in Kaneo (task id `h69p3fiuis7d6xx94vh6sklh`) |
| Branch | `cq-004-backend-skeleton` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

A running FastAPI app with a real settings/DB/error/health foundation and a router-registration pattern, so every feature added from CQ-007 onward plugs in the same way instead of inventing its own wiring.

## Scope

FastAPI app factory, pydantic-settings, async SQLAlchemy session, error model, feature router registry, /health, pytest with test DB, OpenAPI export script.

## Out of scope

- Real domain tables/models (CQ-007).
- Real feature routers besides the `system` health route (CQ-007 onward).
- Frontend API client generation itself (CQ-005) — this item only produces the OpenAPI JSON the generator consumes.
- CI wiring (CQ-006) — this item only makes the commands work locally.

## References

- `docs/design/system-design.md` — "Architecture" (stack decisions), "Emulated integrations" (error-naming precedent later adapters follow).
- `docs/design/data-field-catalog.md` — not applicable (no domain fields yet).
- `AGENTS.md` — Project map (`backend/app/core/`), feature layout (`router.py`, `models.py`, `schemas.py`, `service.py`, `endpoints/`, `tests/`).

## Modules to create (pin exactly)

```
backend/app/
  main.py              create_app() -> FastAPI; module-level `app = create_app()`
  core/
    config.py          Settings(BaseSettings), get_settings() (lru_cache)
    db.py               Base, engine, AsyncSessionLocal, get_db() dependency
    errors.py           AppError and subclasses; register_exception_handlers(app)
    registry.py         FEATURE_ROUTERS list + register_routers(app)
  features/
    system/
      router.py         router = APIRouter(); GET /health
      service.py         run_health_checks() -> HealthReport
      schemas.py         HealthReport, CheckResult (Pydantic)
      tests/
        test_health.py
  scripts/
    export_openapi.py
backend/
  conftest.py            db_session, client, app fixtures shared by every feature's tests/
  tests/
    test_errors.py
    test_registry.py
    test_db_isolation.py
```

## Settings (`backend/app/core/config.py`, pin exactly)

`class Settings(BaseSettings)` reads, by field name (env var in parens): `app_env` (`APP_ENV`), `secret_key` (`SECRET_KEY`), `database_url` (`DATABASE_URL`), `test_database_url` (`TEST_DATABASE_URL`), `valkey_url` (`VALKEY_URL`), `s3_endpoint`, `s3_bucket`, `s3_access_key`, `s3_secret_key`, `s3_region`, `smtp_host`, `smtp_port`, `smtp_from`, `temporal_address`, `temporal_namespace`, `temporal_task_queue`, `cors_origins` (comma-separated → `list[str]`). `model_config = SettingsConfigDict(env_file=".env")`. `get_settings()` is `@lru_cache`d and is what every module imports — never instantiate `Settings()` directly elsewhere.

## DB session (`backend/app/core/db.py`, pin exactly)

- `Base = DeclarativeBase` (SQLAlchemy 2 style); no tables defined here — CQ-007 adds models under each feature's `models.py`, all importing this `Base`.
- `engine = create_async_engine(get_settings().database_url)`.
- `AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)`.
- `async def get_db() -> AsyncIterator[AsyncSession]:` yields a session; used as a FastAPI dependency (`Depends(get_db)`).

## Error model (`backend/app/core/errors.py`, pin exactly)

Base class `AppError(Exception)`: fields `code: str`, `message: str`, `status_code: int = 400`, `details: dict[str, Any] | None = None`. Subclasses (status codes fixed, but a subclass may override `status_code`/`code` per instance — see CQ-009's `PricingValidationError`, which overrides `IntegrationError`'s default 502 to 422): `NotFoundError` (404, code `NOT_FOUND`), `ValidationAppError` (422, code `VALIDATION_ERROR`), `ConflictError` (409, code `CONFLICT`), `AuthenticationError` (401, code `AUTHENTICATION_ERROR` — used by CQ-013's/CQ-014's auth stub/real auth when no credentials are present), `IntegrationError` (502, code `INTEGRATION_ERROR` — the shape CQ-009's mock adapters raise on a forced failure; CQ-009's specific adapter errors subclass this one).

`register_exception_handlers(app: FastAPI)` installs a handler for `AppError` and one for unhandled `Exception` (→ 500, code `INTERNAL_ERROR`). JSON body shape, pinned exactly (every frontend and later backend spec assumes this):

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Application 123 not found",
    "details": {}
  }
}
```

## Router registry (`backend/app/core/registry.py`, pin exactly)

```python
FEATURE_ROUTERS: list[str] = []

def register_routers(app: FastAPI) -> None:
    for module_path in FEATURE_ROUTERS:
        module = import_module(module_path)
        app.include_router(module.router, prefix="/api/v1")
```

`FEATURE_ROUTERS` starts empty — `system` is not a `/api/v1` feature, it is mounted directly (see below), so it never goes in this list. Each feature's `router.py` exposes a module-level `router = APIRouter()`. To add a feature (CQ-007 onward): create the sub-feature package with its own `router.py`, append its dotted path to `FEATURE_ROUTERS`. `create_app()` calls `register_routers(app)` and `register_exception_handlers(app)`, then mounts `/health` directly on `app` via a plain `app.include_router(system_router)` call (not through the registry, and not under `/api/v1` — infra/monitoring hits it unprefixed; `/api/v1/health` must not exist).

## `/health` (pin exactly)

`GET /health`, no auth, no `/api/v1` prefix. Checks: DB (`SELECT 1`), Valkey (`PING` via `redis.asyncio.Redis.from_url(settings.valkey_url)`), MinIO (`boto3` S3 client `head_bucket` against `S3_ENDPOINT`/`S3_BUCKET`), Temporal (`temporalio.client.Client.connect(temporal_address, namespace=temporal_namespace)` with a short timeout). Response body:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "valkey": "ok",
    "minio": "ok",
    "temporal": "ok"
  }
}
```

`status` is `"ok"` only if every check is `"ok"`; otherwise `"degraded"`. A failed check's value is `"error: <short reason>"`. HTTP status is 200 when `status == "ok"`, else 503.

## Test DB fixtures (`backend/conftest.py`, pin exactly)

- `TEST_DATABASE_URL` (database `cq_test` on the same Postgres) backs all tests; no test ever touches `DATABASE_URL`'s database.
- CQ-004 has no real tables yet, so table setup is `Base.metadata.create_all` against an engine bound to `TEST_DATABASE_URL`, run once per test session. **CQ-007 replaces this with `alembic upgrade head` against the test DB** once real models exist — note that explicitly in that item's plan.
- Per-test isolation: a session-scoped engine, a function-scoped `db_session` fixture that opens a connection, begins an outer transaction, binds an `AsyncSession` to that connection, yields the session, then rolls back the outer transaction and closes the connection — so no test's writes survive into the next test, without needing per-test `TRUNCATE`.
- `client` fixture: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` with `app.dependency_overrides[get_db]` pointed at the `db_session` fixture.

## OpenAPI export (`backend/scripts/export_openapi.py`, pin exactly)

Imports `app` from `app.main`, writes `json.dumps(app.openapi(), indent=2)` to `packages/api-client/openapi.json` (creating the file). CQ-005's `make api-client` step consumes this file to generate typed clients — that generation step is CQ-005 scope. Run via `uv run python backend/scripts/export_openapi.py`; takes no CLI flags (the destination path is fixed, not configurable).

## Dev server (pin)

Port `8000` is reserved for this backend's dev server (confirmed free on the reference dev machine; CQ-003's compose stack does not use it). `make api` (added to CQ-002's root Makefile by this item) runs `uv run uvicorn app.main:app --port 8000 --reload`. CQ-005's frontend api-client defaults `NEXT_PUBLIC_API_URL` to `http://localhost:8000` against this port.

## Acceptance criteria

- [ ] AC1 — `/health` reports DB, Valkey, MinIO and Temporal status; the test suite runs against a test DB (roadmap exit check).
- [ ] AC2 — `GET /health` returns the exact JSON shape above; 200 when all four checks are `"ok"`, 503 when any one is monkeypatched to fail.
- [ ] AC3 — `uv run uvicorn app.main:app` boots without error against a running local stack (CQ-003).
- [ ] AC4 — Raising each `AppError` subclass from a test route returns the pinned error JSON shape with its documented status code.
- [ ] AC5 — Adding a second dummy router's dotted path to `FEATURE_ROUTERS` makes its route appear in `app.openapi()["paths"]` without touching `main.py`.
- [ ] AC6 — `backend/scripts/export_openapi.py` writes valid JSON to `packages/api-client/openapi.json` that round-trips through `json.load`.
- [ ] AC7 — Two tests that each insert then roll back a row in the same table don't see each other's data (fixture isolation proven, not assumed).

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC2 | pytest | `backend/app/features/system/tests/test_health.py::test_health_ok`, `::test_health_degraded` |
| AC3 | Manual/shell | `uv run uvicorn app.main:app --port 8000` then `curl localhost:8000/health` |
| AC4 | pytest | `backend/tests/test_errors.py::test_each_apperror_subclass` |
| AC5 | pytest | `backend/tests/test_registry.py::test_dummy_router_registers` |
| AC6 | Shell + pytest | `uv run python backend/scripts/export_openapi.py`, `backend/tests/test_openapi_export.py::test_output_is_valid_json` |
| AC7 | pytest | `backend/tests/test_db_isolation.py::test_rows_do_not_leak_across_tests` |

## Notes for the agent

- Decision: in CI (CQ-006) only Postgres runs as a real service container; Valkey/MinIO/Temporal health checks are tested by monkeypatching their clients, avoiding three more service containers for a skeleton item. Real integration coverage against a live stack is a local (`make up` + manual `curl /health`) check, not a CI gate, until CQ-011 needs Temporal in CI for real.
- Decision: `boto3` (not the `minio` SDK) is the MinIO/S3 client, since `S3_ENDPOINT`/`S3_BUCKET`/`S3_ACCESS_KEY`/`S3_SECRET_KEY` are already AWS-shaped env vars.
- Port `8000` is pinned (see "Dev server" above), not a suggestion; no test depends on it (AC3 uses it directly since it is now reserved for this project).
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
