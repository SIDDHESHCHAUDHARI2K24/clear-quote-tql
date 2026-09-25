# CQ-006 CI

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-004, CQ-005 |
| Kaneo task | CQ-006 in Kaneo (task id `ou6rwxaljifb2qd307wo2v1o`) |
| Branch | `cq-006-ci` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

Every push and pull request gets the same lint/type-check/test signal a human would run locally, on the backend and both frontends, so broken code never lands on `main` unnoticed.

## Scope

GitHub Actions: lint, type-check and tests for backend and frontends.

## Out of scope

- Deployment workflows (CQ-035 — Railway).
- E2E tests against a deployed environment (CQ-036).
- Scheduled/nightly jobs — only `push`/`pull_request` triggers at this phase.

## References

- `docs/design/system-design.md` — "Architecture" (stack decisions: the exact tools CI must run).
- `docs/design/data-field-catalog.md` — not applicable.
- `AGENTS.md` — Commands table (`make lint`, `make test`).

## Workflow file & jobs (pin exactly)

`.github/workflows/ci.yml`. Triggers:

```yaml
on:
  push:
    branches: ["**"]
  pull_request:
```

This runs CI on every branch push and every PR, not only `main` — required so a branch is provably green before merge, per `AGENTS.md`'s Definition of Done.

Two jobs, run in parallel:

**`backend`** (`runs-on: ubuntu-latest`)
- Service container: `postgres`, image `postgres:16-alpine`, env `POSTGRES_USER=cq`, `POSTGRES_PASSWORD=cq`, `POSTGRES_DB=cq_test`, port `5432:5432`, `options: --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 5`.
- Steps: checkout → `astral-sh/setup-uv@v3` (Python 3.12 per `.python-version`) → `uv sync --frozen` → `uv run ruff check backend` → `uv run ruff format --check backend` → `uv run mypy backend/app` → `uv run pytest backend`, with env `TEST_DATABASE_URL=postgresql+asyncpg://cq:cq@localhost:5432/cq_test`, `APP_ENV=test` (so CQ-007's `FIELD_ENCRYPTION_KEY` startup check is skipped, matching `backend/conftest.py`), and dummy values for `VALKEY_URL`/`S3_*`/`TEMPORAL_*` (CQ-004's health checks are monkeypatched in tests, so these never need to resolve in CI).

**`frontend`** (`runs-on: ubuntu-latest`)
- Steps: checkout → `actions/setup-node@v4` with `node-version: 24` → `corepack enable` → `pnpm install --frozen-lockfile` → `pnpm -r run lint` → `pnpm -r run typecheck` → `pnpm exec prettier --check .` → `pnpm -r run test`.

Both jobs must pass for the workflow to be green; branch protection on `main` (human-configured, not part of this item) requires both.

## Acceptance criteria

- [ ] AC1 — CI is green on `main` (roadmap exit check).
- [ ] AC2 — `.github/workflows/ci.yml`'s `on:` block triggers on pushes to every branch and on pull requests, not only `main` — verified by pushing a throwaway branch and seeing a run start.
- [ ] AC3 — The `backend` job runs a `postgres:16-alpine` service container and `uv run pytest backend` passes against it in CI.
- [ ] AC4 — The `backend` job fails the run if `ruff check`, `ruff format --check`, `mypy backend/app`, or `pytest backend` fails (verified by temporarily introducing a lint error on a scratch branch and observing red CI, then reverting).
- [ ] AC5 — The `frontend` job runs `pnpm -r run lint`, `pnpm -r run typecheck`, `prettier --check`, and `pnpm -r run test`, and passes on the CQ-002/CQ-005 empty-project scaffold.
- [ ] AC6 — `actionlint .github/workflows/ci.yml` reports no errors.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1 | CI run | GitHub Actions run on `main` after merge |
| AC2 | CI run | Push a scratch branch (e.g. `ci-trigger-check`), confirm a workflow run starts; delete the branch after |
| AC3 | CI run | Inspect the `backend` job's logs for the `postgres` service and `pytest backend` step |
| AC4 | Manual regression | Temporarily add a ruff violation on a scratch branch, confirm the `backend` job goes red, then revert |
| AC5 | CI run | Inspect the `frontend` job's step logs |
| AC6 | Shell | `actionlint .github/workflows/ci.yml` |

## Notes for the agent

- Decision: no `concurrency:` cancellation group is configured yet — add one (`group: ci-${{ github.ref }}`, `cancel-in-progress: true`) if CI queue times become a problem later; not required for this item's exit check.
- Decision: dummy `VALKEY_URL`/`S3_*`/`TEMPORAL_*` values in the `backend` job's env are placeholders only — CQ-004's tests never actually connect to them (see that spec's Notes). If a later item adds a real integration test needing Valkey/MinIO/Temporal in CI, add service containers for them then rather than widening this item's scope now.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
