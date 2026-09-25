# CQ-004 — Implementation plan

## Decisions & questions (stage 1)

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | `/health` is defined once on `features/system/router.py`'s `router` (per pin) but the spec requires it live both under the registry pattern (`FEATURE_ROUTERS` pins `"app.features.system.router"`, mounted at `/api/v1` by `register_routers`) *and* unprefixed at the app root ("mounts `/health` directly on app... not under `/api/v1`"). | Decided: `create_app()` calls `register_routers(app)` exactly as pinned (produces `/api/v1/health` as a side effect of the pinned registry code) **and** separately does one direct `app.include_router(system_router)` with no prefix for the unprefixed `/health` contract that AC2/AC3 exercise. The harmless duplicate `/api/v1/health` route is documented here rather than deviating from the pinned `registry.py` code. |
| 2 | Decision | `cors_origins` is a comma-separated env var parsed to `list[str]`; pydantic-settings v2 JSON-decodes complex-typed env vars by default, which would fail on a raw comma string. | Decided: add a `field_validator(mode="before")` on `cors_origins` that splits a raw string on commas before pydantic's normal validation runs. |
| 3 | Decision | MinIO check uses `boto3` (sync SDK) inside an async endpoint. | Decided: run `head_bucket` via `asyncio.to_thread` so it doesn't block the event loop. |
| 4 | Decision | AC7's fixture-isolation test needs a real table to insert/rollback, but CQ-004 defines no domain models (CQ-007 scope). | Decided: `test_db_isolation.py` declares a small `Base`-registered throwaway table (`_isolation_probe_cq004`) at module import time; pytest's collect-then-run order means it's present in `Base.metadata` before the session-scoped `create_all` fixture runs. |
| 5 | Decision | Per-test isolation must tolerate a test/app code calling `session.commit()` without ending the outer rollback-able transaction. | Decided: bind the function-scoped `AsyncSession` with `join_transaction_mode="create_savepoint"` (SQLAlchemy 2.0's documented "join a session into an external transaction" recipe), so any inner `commit()` becomes a savepoint release, not a real commit. |
| 6 | Decision | `.env` doesn't exist in a fresh worktree (gitignored); `Settings.model_config` reads `env_file=".env"`. | Decided: no code change — this is expected local dev flow (`cp .env.example .env`). Documented in post-dev "how to test manually". Not committed (gitignored already). |
| 7 | Decision | mypy `disallow_untyped_defs=true` will flag `boto3`/`temporalio` as missing-stubs imports. | Decided: add `[[tool.mypy.overrides]]` for `boto3.*`, `botocore.*` with `ignore_missing_imports = true` if mypy fails on them (temporalio and redis ship inline types). |
| 8 | Decision | ruff's `B008` ("no function calls in argument defaults") flags every `Depends(get_db)` — FastAPI's own DI idiom, which every feature router will use from CQ-007 onward. | Decided: add `ignore = ["B008"]` to `[tool.ruff.lint]`. |
| 9 | Decision | pytest-asyncio's default per-test event loop conflicts with the session-scoped async `test_engine` fixture (asyncpg raises "Future attached to a different loop"). | Decided: set `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"` in `[tool.pytest.ini_options]` so fixtures and tests share one event loop for the whole run. |
| 10 | Decision | pydantic-settings eagerly JSON-decodes complex-typed (`list[str]`) env vars before field validators run, which fails on a raw comma-separated `CORS_ORIGINS` string. | Decided: annotate `cors_origins: Annotated[list[str], NoDecode]` to skip that eager decode, then split on commas in a `mode="before"` field validator. |

No big gaps — spec pins every module, field name, JSON shape and file path exactly.

## Why

Every feature from CQ-007 onward needs a settled app factory, DB session pattern, error shape and router-registration convention instead of inventing its own. This item builds that skeleton plus the `/health` endpoint that proves every backing service (Postgres, Valkey, MinIO, Temporal) from CQ-003 is reachable, and the OpenAPI export CQ-005 consumes.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Settings | `backend/app/core/config.py` |
| DB session | `backend/app/core/db.py` |
| Errors | `backend/app/core/errors.py` |
| Registry | `backend/app/core/registry.py` |
| App factory | `backend/app/main.py` |
| System feature | `backend/app/features/system/{router,service,schemas}.py`, `backend/app/features/system/tests/test_health.py` |
| OpenAPI export | `backend/scripts/export_openapi.py` |
| Shared fixtures | `backend/conftest.py` |
| Root tests | `backend/tests/{test_errors.py,test_registry.py,test_db_isolation.py,test_openapi_export.py}` (drop `test_placeholder.py`) |
| Deps | `pyproject.toml` (fastapi, uvicorn, pydantic-settings, sqlalchemy[asyncio], asyncpg, redis, boto3, temporalio, httpx), `uv.lock` |
| Makefile | add `api` target only |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Add backend deps via `uv add` | — | `pyproject.toml`, `uv.lock` | `uv sync` succeeds |
| T2 | `core/config.py` Settings + `get_settings()` | T1 | `core/config.py` | covered by T3+ tests importing settings |
| T3 | `core/db.py` Base/engine/session/get_db | T2 | `core/db.py` | covered by db_session/isolation tests |
| T4 | `core/errors.py` + handlers | T1 | `core/errors.py` | `backend/tests/test_errors.py` |
| T5 | `core/registry.py` | T1 | `core/registry.py` | `backend/tests/test_registry.py` |
| T6 | `features/system/{schemas,service,router}.py` | T2,T3 | those files | `features/system/tests/test_health.py` |
| T7 | `main.py` app factory | T3,T4,T5,T6 | `main.py` | AC3 manual boot |
| T8 | `backend/conftest.py` shared fixtures | T3,T7 | `conftest.py` | AC7 test |
| T9 | `scripts/export_openapi.py` | T7 | `scripts/export_openapi.py` | `backend/tests/test_openapi_export.py` |
| T10 | `backend/tests/test_db_isolation.py`, drop placeholder | T8 | those files | AC7 |
| T11 | Makefile `api` target | — | `Makefile` | manual |

## Wave schedule (stage 3)

Single agent, sequential (small skeleton item, files interdepend tightly) — no parallel dispatch needed.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1, AC2 | `backend/app/features/system/tests/test_health.py::test_health_ok`, `::test_health_degraded` |
| AC3 | Manual: `uv run uvicorn app.main:app --port 8000` + `curl localhost:8000/health` against `make up` stack |
| AC4 | `backend/tests/test_errors.py::test_each_apperror_subclass` |
| AC5 | `backend/tests/test_registry.py::test_dummy_router_registers` |
| AC6 | `uv run python backend/scripts/export_openapi.py` + `backend/tests/test_openapi_export.py::test_output_is_valid_json` |
| AC7 | `backend/tests/test_db_isolation.py::test_rows_do_not_leak_across_tests` |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6
- [x] T7
- [x] T8
- [x] T9
- [x] T10
- [x] T11
