# CQ-004 — Post-development notes

## Summary

Built the FastAPI app factory (`backend/app/main.py`), settings (`core/config.py`, pydantic-settings), async SQLAlchemy session plumbing (`core/db.py`), the pinned `AppError` hierarchy + JSON error shape (`core/errors.py`), the `FEATURE_ROUTERS` registry (`core/registry.py`), the `system` feature with `GET /health` checking Postgres/Valkey/MinIO/Temporal, `backend/scripts/export_openapi.py`, and shared pytest fixtures (`backend/conftest.py`) giving every future feature's tests a transaction-rollback-isolated `db_session` and an ASGI `client`. All 16 new tests pass against the real local stack (`make up`); `make lint` and `make test` are green repo-wide.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| (implicit) `/health` lives only unprefixed | `/health` (root) and `/api/v1/health` (via registry) both resolve to the same handler | The pinned `registry.py`/`register_routers` code mounts every `FEATURE_ROUTERS` entry (which includes `"app.features.system.router"`, as pinned) under `/api/v1`; `main.py` *also* does a direct unprefixed `include_router` for the `/health` contract. Implementing the pinned registry code literally produces this harmless duplicate route rather than a spec deviation — see plan.md decision 1. |
| No test-infra guidance for `list[str]` env vars | Added `NoDecode` annotation + `mode="before"` validator on `cors_origins` | pydantic-settings v2 eagerly JSON-decodes complex-typed env vars before validators run, which throws on a raw comma string — see plan.md decision 10. |
| — | Added `ignore = ["B008"]` to ruff, `[[tool.mypy.overrides]]` for `boto3.*`/`botocore.*`, and `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope = "session"` to pytest config | Tooling fallout from real deps (FastAPI's `Depends(...)` idiom, boto3 lacking stubs, and pytest-asyncio's per-test-loop default breaking a session-scoped async engine fixture — asyncpg raised "Future attached to a different loop"). See plan.md decisions 8–9. |

None of these change any pinned module name, field name, JSON shape, or endpoint path.

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 | Pass | `uv run pytest backend` → 16 passed, including `test_health.py` against the real `make up` stack (Postgres, Valkey, MinIO, Temporal all `"ok"`) and the whole suite runs against `TEST_DATABASE_URL` (`cq_test`), never `DATABASE_URL`. |
| AC2 | Pass | `test_health_ok` asserts the exact pinned JSON body and HTTP 200; `test_health_degraded` monkeypatches `service.check_valkey` to fail and asserts HTTP 503, `status: "degraded"`, and the other three checks still `"ok"`. |
| AC3 | Pass | Manual: `uv run uvicorn app.main:app --port 8000` against the running `make up` stack booted with no errors (log: "Application startup complete"); `curl localhost:8000/health` → `{"status":"ok","checks":{"database":"ok","valkey":"ok","minio":"ok","temporal":"ok"}}`, HTTP 200. Server stopped afterward (`pkill -f "uvicorn app.main:app"`), confirmed via a failed follow-up curl. |
| AC4 | Pass | `backend/tests/test_errors.py::test_each_apperror_subclass` (parametrized over all 5 subclasses) asserts each documented status code + `code`; `test_unhandled_exception_returns_internal_error` covers the generic-`Exception` → 500/`INTERNAL_ERROR` handler; `test_apperror_status_and_code_can_be_overridden_per_instance` proves the CQ-009-style per-instance override. |
| AC5 | Pass | `backend/tests/test_registry.py::test_dummy_router_registers` monkeypatches `FEATURE_ROUTERS` to append `"tests._dummy_feature_router"`, calls `create_app()` (no `main.py` edits), and asserts `/api/v1/dummy` is in `app.openapi()["paths"]`. |
| AC6 | Pass | `uv run python backend/scripts/export_openapi.py` → wrote to `packages/api-client/openapi.json`; manually verified `openapi: "3.1.0"`, `paths: ["/api/v1/health", "/health"]`, and the `HealthReport` schema matches the pinned shape exactly. `backend/tests/test_openapi_export.py::test_output_is_valid_json` round-trips through `json.load` against a `tmp_path` destination (kept out of the real path so `pytest` never writes into `packages/`). The real generated file was deleted before commit per this item's parallel-work instructions (CQ-005 owns a hand-written stub there until the orchestrator runs `make api-client` post-merge). |
| AC7 | Pass | `backend/tests/test_db_isolation.py::test_rows_do_not_leak_across_tests` opens two independent connection+transaction+session flows against the same `_isolation_probe_cq004` table and proves the second sees none of the first's committed-then-rolled-back row; `test_db_session_fixture_itself_rolls_back`/`test_previous_fixture_test_left_no_trace` prove the same for the actual `db_session` fixture across two real, separate pytest tests. |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `uv run pytest backend` | 16 passed (run twice back-to-back for determinism) |
| Backend lint | `uv run ruff check backend` | All checks passed |
| Backend format | `uv run ruff format --check backend` | 23 files already formatted |
| Backend types | `uv run mypy backend/app` (Makefile scope) and `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` (full) | Success: no issues found |
| Full repo lint | `make lint` | ruff/mypy/eslint/tsc/prettier all green (required `pnpm install` first — `node_modules` wasn't present in this fresh worktree; gitignored, no repo changes) |
| Full repo test | `make test` | pytest 16 passed; `pnpm -r run test` — 4 workspace test files passed (pre-existing CQ-002/CQ-005-scaffold placeholder tests) |
| Manual boot | `uv run uvicorn app.main:app --port 8000` + `curl localhost:8000/health` | 200, all four checks `"ok"`; server stopped after |
| OpenAPI export | `uv run python backend/scripts/export_openapi.py` | Valid JSON written and inspected, then deleted (not committed, per parallel-work rules) |

## Review findings (stage 6)

_(left empty — a fresh subagent reviewer fills this in.)_

## How to test manually

1. `cp .env.example .env` (once per worktree; gitignored).
2. `make up` (starts Postgres/Valkey/MinIO/Mailpit/Temporal on the reserved ports).
3. `uv run pytest backend` — all pass against the live stack's `cq_test` database.
4. `make api` (or `uv run uvicorn app.main:app --port 8000 --reload`), then `curl localhost:8000/health`.
5. `uv run python backend/scripts/export_openapi.py`, inspect `packages/api-client/openapi.json`, then `rm` it (don't commit — CQ-005 owns a stub there until the orchestrator runs `make api-client` post-merge).
6. `make down` when finished.

## Follow-ups

- CQ-007 replaces `Base.metadata.create_all` in `backend/conftest.py`'s `test_engine` fixture with `alembic upgrade head` against the test DB, and can remove the throwaway `_isolation_probe_cq004` table/test once real models exist to prove isolation against.
- CQ-006 (CI): only Postgres needs to run as a real service container per this item's plan.md decision — Valkey/MinIO/Temporal are covered locally via `make up` + manual `curl /health`, not in CI, until CQ-011 needs a real Temporal service in CI.
- The harmless `/api/v1/health` duplicate (plan.md decision 1) is worth a one-line mention if a later item ever audits the OpenAPI path list.
