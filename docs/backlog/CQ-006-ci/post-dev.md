# CQ-006 — Post-development notes

## Summary

Added `.github/workflows/ci.yml` with two parallel jobs (`backend`, `frontend`) triggered on every branch push and every pull request, per spec.md's pinned trigger/step list. `backend` runs a real `postgres:16-alpine` service container and `ruff check`/`ruff format --check`/`mypy backend/app`/`pytest backend`; `frontend` runs `pnpm -r run lint`/`typecheck`, `prettier --check .`, and `pnpm -r run test`. Added `permissions: contents: read`, a `concurrency` cancel-in-progress group, and caching for both `uv` (built-in `enable-cache`) and `pnpm` (`actions/cache@v4` keyed on `pnpm-lock.yaml`), none of which change the pinned command list. No pushing/PR was performed (not authorized to push); every job's steps were instead emulated locally with the same commands and environment variables, against a real local Postgres via `make up`, and `actionlint` was run against the workflow file directly. One pre-existing bug in already-merged CQ-004 test code was found during this validation (see Deviations) and is flagged, not fixed, since it's outside this item's edit scope.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| No explicit `permissions:`/`concurrency:` in the YAML skeleton | Added `permissions: contents: read` and `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` | Orchestrator's brief for this item requires least-privilege permissions and a cancel-in-progress concurrency group; spec's Notes explicitly leave `concurrency` optional/deferrable, this doesn't conflict, just adopts it now |
| Spec's step list has no explicit caching | Added `enable-cache: true` to `astral-sh/setup-uv@v3` and a `pnpm store path` + `actions/cache@v4` pair before `pnpm install` | Orchestrator's brief requires caching for uv and pnpm; doesn't change or reorder the pinned lint/type/test commands, only wraps dependency installation |
| — | `actions/checkout@v4` used (not pinned by spec) | Spec doesn't name a checkout action version; `v4` is current stable, consistent style with the `@v3`/`@v4` pins spec does give |
| Spec's Notes: "CQ-004's health checks are monkeypatched in tests, so these never need to resolve in CI" | Not true of the merged code — see below | Pre-existing bug in CQ-004, found during local emulation of the `backend` job, not a CQ-006 decision |

### Flagged issue (not fixed — out of this item's scope)

`backend/app/features/system/tests/test_health.py::test_health_ok` does **not** monkeypatch `check_valkey`/`check_minio`/`check_temporal` — it exercises the real `boto3`/`redis`/`temporalio` clients against `VALKEY_URL`/`S3_*`/`TEMPORAL_*`. `test_health_degraded` only monkeypatches `check_valkey`, and only in the failure-path test. CQ-004's own `spec.md` (Notes) states the intended design: "in CI (CQ-006) only Postgres runs as a real service container; Valkey/MinIO/Temporal health checks are tested by monkeypatching their clients" — the merged code doesn't do this for the happy-path test. Because CQ-006's `backend` job (per spec.md, correctly) only runs a Postgres service container, `test_health_ok` will fail on a real GitHub Actions run with dummy `VALKEY_URL`/`S3_*`/`TEMPORAL_*` (confirmed locally — see Test log). This is a bug in already-merged CQ-004 code; `test_health.py` is outside CQ-006's edit scope (`.github/` + this item's own docs folder only), so it was flagged here and in the final report rather than patched.

**Suggested fix** (for the CQ-004 owner or orchestrator to apply): in `test_health_ok`, monkeypatch `check_minio` and `check_temporal` (in addition to `check_valkey`) to return `CheckResult(name=..., status="ok")`, mirroring the `_failing_valkey_check` pattern already used in `test_health_degraded`.

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — CI green on `main` | **Pending — orchestrator verifies after push** | Not evidenceable from this worktree; per orchestrator, `main`/`phase-p0-p1` are on `origin` and the orchestrator will push this branch and read the real run. |
| AC2 — triggers on every branch push + PR | Pass (static) / Pending (live trigger) | `.github/workflows/ci.yml`'s `on:` block matches spec.md verbatim: `push.branches: ["**"]`, `pull_request` (no branch filter). Confirmed with `actionlint` (no errors) and a read of the file. A live scratch-branch push to observe a run starting was not performed — pushing is reserved for the orchestrator. |
| AC3 — `backend` job's postgres service + `uv run pytest backend` passes | **Partial** — see caveat | Local emulation: `docker compose -f infra/docker-compose.yml up -d --wait` (same `postgres:16-alpine` image/creds/db as the job's service container) + `uv run pytest backend` with the job's exact env vars: 14 passed, 2 failed (`test_health.py::test_health_ok`, `::test_health_degraded`) — both failures are the pre-existing CQ-004 bug above, not a CI-config problem. Re-run with all four backing services pointed at real local infra (matching `.env.example`): **16 passed**, confirming the Postgres integration and every other test pass; only the two health-check tests need the CQ-004 fix to go green in a real GitHub Actions runner. |
| AC4 — backend job fails on ruff/format/mypy/pytest failure | Pass | Added `import os` unused mid-file to `backend/app/features/system/service.py`: `uv run ruff check backend` → exit 1 (E402, F401). Reverted (`git checkout --`), confirmed exit 0 again. Added `x=1` (misformatted): `uv run ruff format --check backend` → exit 1 ("1 file would be reformatted"). Reverted. Working tree confirmed clean after (`git status --short`). |
| AC5 — frontend job runs lint/typecheck/prettier/test, passes on the scaffold | Pass | From repo root: `pnpm install --frozen-lockfile` (480 packages, from lockfile, no changes) → `pnpm -r run lint` (4/4 workspaces, no errors) → `pnpm -r run typecheck` (4/4 workspaces, no errors) → `pnpm exec prettier --check .` ("All matched files use Prettier code style!") → `pnpm -r run test` (4/4 workspaces: 34 tests passed across `@cq/ui`, `@cq/api-client`, `lo-console`, `borrower-portal`). |
| AC6 — `actionlint` reports no errors | Pass | `actionlint .github/workflows/ci.yml` → no output, exit 0 |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| actionlint | `actionlint .github/workflows/ci.yml` | Clean, exit 0 |
| Backend — ruff check | `uv run ruff check backend` (CI env) | All checks passed |
| Backend — ruff format | `uv run ruff format --check backend` (CI env) | 23 files already formatted |
| Backend — mypy | `uv run mypy backend/app` (CI env) | Success: no issues found in 14 source files |
| Backend — pytest (CI-realistic dummy env) | `uv run pytest backend` (`APP_ENV=test`, dummy `VALKEY_URL`/`S3_*`/`TEMPORAL_*`, real `TEST_DATABASE_URL` against `make up` Postgres) | 14 passed, 2 failed (`test_health.py` — pre-existing CQ-004 bug, see Deviations) |
| Backend — pytest (real infra env) | `uv run pytest backend` (same, but `VALKEY_URL`/`S3_*`/`TEMPORAL_*` pointed at the real local `make up` stack) | 16 passed |
| Backend — AC4 regression (ruff check) | Introduced unused import, re-ran `uv run ruff check backend`, reverted | Failed as expected (exit 1), then passed again after revert |
| Backend — AC4 regression (ruff format) | Introduced misformatted line, re-ran `uv run ruff format --check backend`, reverted | Failed as expected (exit 1), then passed again after revert |
| Frontend — install | `pnpm install --frozen-lockfile` | Lockfile up to date, 480 packages |
| Frontend — lint | `pnpm -r run lint` | 4/4 workspaces pass |
| Frontend — typecheck | `pnpm -r run typecheck` | 4/4 workspaces pass |
| Frontend — prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| Frontend — test | `pnpm -r run test` | 4/4 workspaces, 34 tests passed |

## Review findings (stage 6)

(left empty for the fresh reviewer, per AGENTS.md stage 6)

## How to test manually

1. `docker compose -f infra/docker-compose.yml up -d --wait` (or `make up`).
2. Export the `backend` job's env vars from `.github/workflows/ci.yml` (or use real `.env.example` values if a full local stack is running) and run: `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend/app && uv run pytest backend`.
3. From repo root: `pnpm install --frozen-lockfile && pnpm -r run lint && pnpm -r run typecheck && pnpm exec prettier --check . && pnpm -r run test`.
4. `actionlint .github/workflows/ci.yml` should report nothing.

## Follow-ups

- Fix `backend/app/features/system/tests/test_health.py::test_health_ok` to monkeypatch `check_valkey`/`check_minio`/`check_temporal` (see Deviations above) — otherwise the real GitHub Actions `backend` job will go red on its first run for a reason unrelated to this item's CI config.
- Once the human configures branch protection on `main` requiring both `backend` and `frontend` jobs (out of scope for this item, per spec.md), AC1's exit check is fully closed.
- If a later item needs Valkey/MinIO/Temporal in CI for real integration coverage, add service containers then (per CQ-004's spec.md Decision) rather than widening this item retroactively.
