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

Reviewed by a fresh subagent (did not write this code) against `spec.md`, `plan.md`, `AGENTS.md`, and `docs/design/system-design.md`.

### Commands re-run

| Command | Result |
| --- | --- |
| `make up` (project `clear-quote`; `kaneo-evaluation-*` untouched) | Pass — all 6 services healthy |
| `cp .env.example .env` | Not needed — `.env` already present in worktree, confirmed untracked (`git ls-files .env` empty; `.gitignore:8` ignores it) |
| `pnpm install` | Not needed — `node_modules` already present |
| `uv sync` | Pass |
| `uv run pytest backend -q` | Pass — 16 passed |
| `make lint` | Pass — ruff, ruff format, mypy (`backend/app`), eslint, tsc, prettier all clean |
| `make test` | Pass — pytest 16 passed; `pnpm -r run test` 4 files passed |
| `uv run uvicorn app.main:app --app-dir backend --port 8000` + `curl localhost:8000/health` | Pass — HTTP 200, all four checks `"ok"`; server stopped after |
| `curl localhost:8000/openapi.json` inspected for `operationId` collisions | No literal collision (`get_health_health_get` vs `get_health_api_v1_health_get`), but see finding #1 |
| `make down` (no `-v`) | Ran at end of review |

### Findings

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | Major | `backend/app/main.py:32-37`, `backend/app/core/registry.py:13-15`, `backend/tests/test_registry.py:22-27` | Spec pins, verbatim: `create_app()` "mounts `/health` directly on app (not through the registry, and not under `/api/v1`)". Because `"app.features.system.router"` is also the one entry in the pinned `FEATURE_ROUTERS` list, `register_routers` additionally mounts it at `/api/v1/health`. Confirmed live: `GET /api/v1/health` returns 200 and both paths appear in `app.openapi()["paths"]`. This is a genuine contract violation (spec explicitly says "not under `/api/v1`"), not just a style nit — it pollutes the OpenAPI schema `packages/api-client/openapi.json` will hold, so CQ-005's generated client gets two functions for one conceptual endpoint (`getHealthHealthGet` and `getHealthApiV1HealthGet`). `test_system_router_is_mounted_unprefixed_and_registered` locks in the extra path as intended behavior rather than testing the pinned contract. plan.md decision 1 documents this as a conscious choice, but a real contradiction in the spec's own pins (FEATURE_ROUTERS must literally contain the system router; `/health` must never appear under `/api/v1`) is a "big gap" under AGENTS.md's stage-1 rule ("Big gaps → Kaneo comment + `needs-input`, stop"), not a "small gap with data available." | Either drop `include_in_schema=False` on the `/api/v1` mount so the duplicate never reaches the OpenAPI schema/generated client, or don't route the system module through `FEATURE_ROUTERS` at all (mount it only via the direct unprefixed `include_router` call) and keep `FEATURE_ROUTERS` empty until CQ-007's first real feature. At minimum, raise the pin contradiction in Kaneo per AGENTS.md rather than resolving it unilaterally in `plan.md`. |
| 2 | Minor | `backend/app/features/system/schemas.py:11-13` | `CheckResult` is defined per the spec's module pin ("`schemas.py` HealthReport, CheckResult (Pydantic)") but is never used anywhere — `HealthReport.checks` is `dict[str, CheckStatus]` (`CheckStatus = str`), not `dict[str, CheckResult]`. Dead code. | Either use `CheckResult` in `HealthReport.checks` (matching the two-field `name`/`status` shape) or drop it if the flat `dict[str, str]` shape in the spec's pinned JSON example is intentional and `CheckResult` was just scaffolding. |
| 3 | Minor | `Makefile:14-19` (`lint` target), `pyproject.toml` (`[tool.mypy] packages = ["app"]`) | `make lint`'s mypy step only type-checks `backend/app`; `backend/conftest.py`, `backend/tests/`, and `backend/scripts/export_openapi.py` (a pinned CQ-005 dependency) are never type-checked by the lint gate. Currently clean (`uv run mypy backend/conftest.py backend/tests backend/scripts` → no issues), so no live bug, but it's a coverage gap in the gate itself. | Add `backend/conftest.py backend/tests backend/scripts` to the `mypy` invocation in `make lint`, or a second mypy line for them. |
| 4 | Nit | `docs/backlog/CQ-004-backend-skeleton/post-dev.md` "Deviations from spec" table | The `/api/v1/health` duplicate is described as "(implicit)" and "not a spec deviation" — but the spec's wording ("not under `/api/v1`") is explicit, not implicit. Understates finding #1 for a future auditor skimming this table. | Reword to acknowledge the explicit pin is contradicted, not just an implicit assumption. |

No critical findings. AC1–AC7 are each backed by a real, meaningful test and all pass; error-handler 500 path never leaks exception text; CORS parsing (`NoDecode` + `mode="before"` validator) works correctly for the comma-separated env var; DB test isolation genuinely rolls back (proven with three sequential probes plus two real separate pytest tests); no secrets committed (`.env` untracked, `.env.example` holds only local-mock placeholder values); no real provider calls (health checks hit only the `make up` mocks).

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
