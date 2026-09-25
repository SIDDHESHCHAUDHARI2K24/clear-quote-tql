# CQ-002 Monorepo scaffold

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-001 |
| Kaneo task | CQ-002 in Kaneo (task id `disw1i8c7oxu9qzxz0zii13j`) |
| Branch | `cq-002-monorepo-scaffold` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

One command (`make lint` / `make test`) runs cleanly across a fully laid-out but empty monorepo, so every later item adds code to a fixed skeleton instead of arguing about paths, package names or tool config.

## Scope

pnpm workspaces (apps/lo-console, apps/borrower-portal, packages/ui, packages/api-client), uv backend project, root alembic/, Makefile, pre-commit, ruff, eslint, prettier, .env.example.

## Out of scope

- Real FastAPI app, DB session, routers (CQ-004).
- Docker Compose services (CQ-003).
- Design tokens, shared components, real Next.js pages (CQ-005).
- CI workflow (CQ-006) — this item only makes `make lint`/`make test` work locally.
- Real Alembic migrations and models (CQ-007) — `alembic/` exists with `env.py` wired to the (empty) `app` package and `alembic.ini`, but no `versions/` yet.

## References

- `docs/design/system-design.md` — "Architecture" (repo layout, stack decisions table).
- `docs/design/data-field-catalog.md` — not applicable (infra item, no domain fields).
- `AGENTS.md` — Project map, Commands table.

## Directory layout (pin exactly)

```
Total Quality Lending/                 (repo root)
  .python-version                      "3.12"
  pyproject.toml                       single uv project, package = backend/app
  uv.lock
  pnpm-workspace.yaml
  package.json                         private, workspaces root
  Makefile
  .env.example
  .pre-commit-config.yaml
  .gitignore
  alembic/
    env.py                             imports app.core.db:Base, app.core.config:get_settings
    script.py.mako
    versions/                          empty until CQ-007
  alembic.ini
  backend/
    app/
      __init__.py
      core/                            config.py, db.py, errors.py, registry.py (real code lands CQ-004)
      integrations/                    empty, one dir per provider from CQ-009
      features/                        empty, one dir per feature from CQ-004 (system/) onward
      workflows/                       empty, Temporal worker added CQ-011
    scripts/                           export_openapi.py added CQ-004
    tests/
      test_placeholder.py              asserts True, keeps pytest green until CQ-004
  apps/
    lo-console/                        Next.js App Router, TypeScript
    borrower-portal/                   Next.js App Router, TypeScript
  packages/
    ui/                                design tokens + shared components (CQ-005)
    api-client/                        generated OpenAPI client (CQ-004/CQ-005)
  seed/                                empty, generators added CQ-010
  infra/
    docker-compose.yml                 added CQ-003
  docs/                                already present
```

## Workspace package names (pin exactly)

| Path | `name` in package.json | Private |
| --- | --- | --- |
| repo root | `clear-quote` | true |
| `apps/lo-console` | `@cq/lo-console` | true |
| `apps/borrower-portal` | `@cq/borrower-portal` | true |
| `packages/ui` | `@cq/ui` | true |
| `packages/api-client` | `@cq/api-client` | true |

`pnpm-workspace.yaml`:
```yaml
packages:
  - "apps/*"
  - "packages/*"
```
Root `package.json` pins `"packageManager": "pnpm@9.15.4"` and `"engines": { "node": ">=20" }` (dev machine runs Node 24; CI matches).

## Python project (pin exactly)

- One uv project at repo root: `pyproject.toml` with `[tool.hatch.build.targets.wheel] packages = ["backend/app"]`, so the importable package is `app` (e.g. `from app.core.config import get_settings`), physically at `backend/app/`. No separate `backend/pyproject.toml`.
- `.python-version` = `3.12` (uv provisions this interpreter regardless of the system pyenv version).
- All backend commands run from repo root via `uv run …` (e.g. `uv run pytest backend`, `uv run alembic upgrade head`).
- `[tool.ruff]`: `line-length = 100`, `target-version = "py312"`, `src = ["backend"]`, select at least `E, F, I, UP, B`.
- `[tool.mypy]`: `python_version = "3.12"`, `mypy_path = "backend"`, `packages = ["app"]`. Decision: start with `disallow_untyped_defs = true` only (not full `strict`); tighten later if it stays cheap.
- `[tool.pytest.ini_options]`: `testpaths = ["backend"]`, `pythonpath = ["backend"]`.
- `alembic/env.py` imports `from app.core.db import Base` and `from app.core.config import get_settings`; `alembic.ini`'s `sqlalchemy.url` is left blank and set at runtime from `DATABASE_URL` inside `env.py` (real models land in CQ-007).

## `.env.example` (repo root, pin exactly these keys)

```
APP_ENV=local
SECRET_KEY=change-me

DATABASE_URL=postgresql+asyncpg://cq:cq@localhost:5432/cq_dev
TEST_DATABASE_URL=postgresql+asyncpg://cq:cq@localhost:5432/cq_test

VALKEY_URL=redis://localhost:6379/0

S3_ENDPOINT=http://localhost:9010
S3_BUCKET=clear-quote
S3_ACCESS_KEY=cq-minio
S3_SECRET_KEY=cq-minio-secret
S3_REGION=us-east-1

SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_FROM=noreply@clearquote.local

TEMPORAL_ADDRESS=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=clear-quote-pipeline

CORS_ORIGINS=http://localhost:3010,http://localhost:3020
```
These values match the compose ports pinned in CQ-003's spec; CQ-003 must not change a name or default here without updating this file. `apps/lo-console` and `apps/borrower-portal` `dev` scripts run on `3010`/`3020` respectively (`next dev -p 3010` / `-p 3020`, pinned by CQ-005, which owns the frontend dev-port choice) — port `3000` is already in use by something else on the reference dev machine. Port `8000` is reserved for the backend API dev server (CQ-004 owns `make api` / `uv run uvicorn app.main:app --port 8000`).

**Env vars added by later items (do not duplicate here at CQ-002 time; each introducing item appends its own key to this file and says so in its own spec):** `FIELD_ENCRYPTION_KEY` (CQ-007), `INTEGRATION_LATENCY_ENABLED` (CQ-009), `SEED_FAST_ADAPTERS` (CQ-010), `DEV_LO_ID` (CQ-013). `NEXT_PUBLIC_API_URL` is a frontend-only var read by the Next.js apps (default `http://localhost:8000`, CQ-005) and lives in each app's own `.env.local`/`.env.example`, not this root backend file.

## Makefile targets (pin exactly what each runs)

| Target | Runs |
| --- | --- |
| `make up` | `docker compose -f infra/docker-compose.yml up -d --wait` (real behaviour lands in CQ-003; until then the target exists and fails loudly if `infra/docker-compose.yml` is missing) |
| `make down` | `docker compose -f infra/docker-compose.yml down` |
| `make logs` | `docker compose -f infra/docker-compose.yml logs -f` |
| `make lint` | `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend/app && pnpm -r run lint && pnpm -r run typecheck && pnpm exec prettier --check .` |
| `make test` | `uv run pytest backend && pnpm -r run test` |
| `make api-client` | `uv run python backend/scripts/export_openapi.py && pnpm --filter @cq/api-client run generate` (both scripts are placeholders until CQ-004/CQ-005 exist) |
| `make demo-reset` | Placeholder: prints `"demo-reset: not implemented until CQ-010"` and exits 0 (CQ-010 replaces the body) |
| `make api` | *(added by CQ-004)* `uv run uvicorn app.main:app --port 8000 --reload` — not part of this item's scope, listed so later items don't invent a second name |
| `make worker` | *(added by CQ-011)* `cd backend && uv run python -m app.workflows.worker` — not part of this item's scope, listed so later items don't invent a second name |

## Lint tooling (pin exactly)

- Backend: ruff (lint + format), mypy — both configured in root `pyproject.toml`.
- Frontend: ESLint flat config at repo root (`eslint.config.mjs`) extending `eslint-config-next` for both apps; Prettier config `.prettierrc.json` at repo root; each app/package exposes `"lint"` and `"typecheck"` (`tsc --noEmit`) scripts so `pnpm -r run lint` / `pnpm -r run typecheck` work workspace-wide.
- `.pre-commit-config.yaml`: `ruff` + `ruff-format` (via `astral-sh/ruff-pre-commit`) and the generic hooks `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`. Decision: pre-commit stays Python-only; JS lint/format run via `make lint`, not pre-commit, so hook install doesn't need Node.

## Acceptance criteria

- [ ] AC1 — `make lint` and `make test` pass on the empty projects (roadmap exit check).
- [ ] AC2 — The directory layout above exists exactly; `find backend/app apps packages alembic -maxdepth 2` matches it.
- [ ] AC3 — `pnpm ls -r --depth -1 --json` lists exactly `@cq/lo-console`, `@cq/borrower-portal`, `@cq/ui`, `@cq/api-client`.
- [ ] AC4 — `uv sync` succeeds from repo root; `uv run python -c "import app"` succeeds.
- [ ] AC5 — `.env.example` contains every key listed above, spelled exactly as listed.
- [ ] AC6 — `make up`, `make down`, `make logs`, `make api-client`, `make demo-reset` all exist as Makefile targets; `make demo-reset` prints the placeholder message and exits 0.
- [ ] AC7 — `pre-commit run --all-files` passes.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | Command | `make lint`, `make test` |
| AC2 | Command | `find backend/app apps packages alembic -maxdepth 2 \| sort` (diff against this spec) |
| AC3 | Command | `pnpm ls -r --depth -1 --json \| jq '[.[].name]'` |
| AC4 | Command | `uv sync && uv run python -c "import app"` |
| AC5 | Command | `grep -E '^[A-Z0-9_]+=' .env.example \| wc -l` (≥ 16) |
| AC6 | Command | `make demo-reset; echo $?` |
| AC7 | Command | `pre-commit run --all-files` |

## Notes for the agent

- Decision: `backend/tests/test_placeholder.py` (one `assert True`) exists only to keep `pytest backend` and ruff/mypy green before CQ-004 adds real modules; delete it once CQ-004 lands real tests.
- Decision: `make api-client` and `make up` are defined now but only fully work once CQ-003/CQ-004/CQ-005 land; don't block this item's exit on them doing real work, only on existing and failing loudly (not silently) if their dependency is missing.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
