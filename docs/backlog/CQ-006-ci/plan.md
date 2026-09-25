# CQ-006 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

Gap check against spec.md: the spec is unusually prescriptive (it pins the workflow filename, triggers, both jobs' steps and env vars almost verbatim). No big gaps found. Small gaps below.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | `actions/checkout` version not pinned by spec | Use `actions/checkout@v4` (current stable major, SHA-independent pin via tag, consistent with the `@v3`/`@v4` style the spec already uses for the other two actions). |
| 2 | Decision | Caching for uv/pnpm not in spec's step list, but required by the orchestrator brief | Add `enable-cache: true` to `astral-sh/setup-uv@v3` (its built-in, official caching, keyed off `uv.lock`) — no extra step needed. For pnpm, insert two small steps between `corepack enable` and `pnpm install --frozen-lockfile`: resolve `pnpm store path` and cache it with `actions/cache@v4` keyed on `pnpm-lock.yaml`'s hash. Neither addition changes the pinned command list the spec cares about (ruff/mypy/pytest/lint/typecheck/test/prettier), it only wraps them with caching. |
| 3 | Decision | `permissions:` and `concurrency:` not in the spec's YAML skeleton | Spec's own Notes section explicitly defers `concurrency:` as optional ("not required for this item's exit check") but the orchestrator's brief requires it for this item, so add `concurrency: group: ci-${{ github.ref }}, cancel-in-progress: true` at the workflow level. Add top-level `permissions: contents: read` (least privilege — no job needs to write). |
| 4 | Decision | Full env var list for the `backend` job | Spec only calls out `TEST_DATABASE_URL` and `APP_ENV` explicitly ("and dummy values for `VALKEY_URL`/`S3_*`/`TEMPORAL_*`"). `backend/app/core/config.py` (CQ-004, merged) is a pydantic `BaseSettings` that also requires `secret_key`, `database_url`, `smtp_host`, `smtp_port`, `smtp_from` with no defaults, or `Settings()` raises at import time before any test runs. Filled these in as dummy CI values mirroring `.env.example`'s shape (never real secrets — this is a mock-only prototype). |
| 5 | Decision | `uv run mypy backend/app` (spec) vs `make lint`'s wider `backend/app backend/conftest.py backend/tests backend/scripts` | Spec says "pin exactly" for the workflow jobs section, so the CI step uses the narrower `uv run mypy backend/app` verbatim from spec.md, not `make lint`'s wider path list. Not calling `make lint`/`make test` directly from CI — spec pins the individual commands per job instead of the Makefile targets, so CI step failures point at exactly one tool. |
| 6 | Decision | Root `prettier --check .` scope | Spec pins `pnpm exec prettier --check .` (matches `make lint`'s last line) — run as-is; `.prettierignore` (already in repo) scopes out generated/build output. |
| 7 | Decision | CI validation without pushing | Per orchestrator instruction: do not push or open a PR. Validate with `actionlint` (installed via `brew install actionlint`) and by running every job's steps locally with the same commands/env against a local Postgres (via `make up`), recording output in `post-dev.md`. AC1 ("CI green on main") is marked Pending — requires human-approved push. |
| 8 | Bug found, then **orchestrator-authorised fix applied** | `backend/app/features/system/tests/test_health.py::test_health_ok` did not monkeypatch `check_valkey`/`check_minio`/`check_temporal` — it hit real infra, contradicting CQ-004's own spec.md ("Valkey/MinIO/Temporal health checks are tested by monkeypatching their clients"). Initially flagged and left unfixed (outside this item's `.github/`+docs scope). Orchestrator authorised a scope extension to fix it on this branch. Applied: `test_health_ok` and `test_health_degraded` now share a `_patch_non_db_checks_ok` helper that monkeypatches `check_valkey`/`check_minio`/`check_temporal` to `"ok"`; `test_health_degraded` then overrides `check_valkey` back to a failure, same as before. Verified with the CI job's exact dummy env: 16/16 pass. |
| 9 | Orchestrator-authorised | CI `backend` job's mypy step widened from `uv run mypy backend/app` to `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts`, matching `make lint`'s scope exactly (CQ-004 widened `make lint`'s mypy coverage after CQ-006's spec.md was written) so the two can't drift. Verified: `Success: no issues found in 23 source files`. |

## Why

CQ-004 (backend) and CQ-005 (frontends) are merged with real lint/type-check/test commands (`make lint`, `make test`). Nothing currently runs those on push/PR, so a broken commit could land on `main` unnoticed. This item wires GitHub Actions so every push/PR gets backend (ruff, mypy, pytest against a real Postgres service container) and frontend (eslint, tsc, prettier, vitest) signal automatically.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| CI workflow | create `.github/workflows/ci.yml` |
| Backlog docs | `docs/backlog/CQ-006-ci/plan.md`, `post-dev.md`, `handoff.md` (this item only); `docs/backlog/README.md` status row |

No application code changes — CQ-006 is CI wiring only, per AGENTS.md's "only edit `.github/` and your own docs folder" scope for this item.

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Write `.github/workflows/ci.yml` (triggers, permissions, concurrency, `backend` job, `frontend` job) | — | `.github/workflows/ci.yml` | `actionlint .github/workflows/ci.yml` (AC6) |
| T2 | Validate `backend` job locally: bring up Postgres via `make up`, run each pinned command with the job's exact env | T1 | — | Local run of ruff/mypy/pytest against `cq_test` (AC3, AC4) |
| T3 | Validate `frontend` job locally: run each pinned command from repo root | T1 | — | Local run of eslint/tsc/prettier/vitest (AC5) |
| T4 | Regression-check AC4: temporarily break a rule, confirm the exact command fails, revert | T1, T2 | — | `uv run ruff check backend` on a scratch edit, reverted before commit |
| T5 | Fill `post-dev.md` with test log + acceptance evidence; mark AC1/AC2 as Pending (require a human-approved push) | T1–T4 | `post-dev.md` | — |

## Wave schedule (stage 3)

| Wave | Tasks (run in parallel) | Why this order |
| --- | --- | --- |
| 1 | T1 | The workflow file is the only artifact; everything else validates it |
| 2 | T2, T3 (sequential in one agent — no parallelism benefit for a single-file item) | Both depend on T1 |
| 3 | T4, T5 | Regression check and writeup depend on a working baseline from wave 2 |

Single implementer (this agent), no subagent dispatch needed — one file, no independent concurrent workstreams.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 — CI green on `main` | Cannot be evidenced without a human-approved push (per orchestrator instruction). Marked Pending in post-dev.md. |
| AC2 — triggers on every branch push + PR | Static: `.github/workflows/ci.yml`'s `on:` block matches spec verbatim (`push.branches: ["**"]`, `pull_request`). No scratch-branch push performed (no push allowed this session) — documented as Pending/deferred to human push, same as AC1. |
| AC3 — `backend` job's postgres service + `uv run pytest backend` passes | Local emulation: `make up` (real `postgres:16-alpine` via compose, same image/creds/db as the spec's service container) + `uv run pytest backend` with the job's exact env vars |
| AC4 — backend job fails on ruff/ruff format/mypy/pytest failure | Local emulation: introduce one ruff violation on a scratch file, run `uv run ruff check backend`, confirm non-zero exit, revert; same for the other three commands (confirm they currently pass, i.e. would not spuriously fail the job) |
| AC5 — frontend job runs lint/typecheck/prettier/test and passes on the empty scaffold | Local emulation: `pnpm install --frozen-lockfile`, `pnpm -r run lint`, `pnpm -r run typecheck`, `pnpm exec prettier --check .`, `pnpm -r run test` from repo root |
| AC6 — `actionlint` reports no errors | `actionlint .github/workflows/ci.yml` |

## Progress

- [x] T1
- [x] T2 (fixed per decisions #8, #9 — 16/16 pass with CI's exact dummy env)
- [x] T3
- [x] T4
- [x] T5
- [x] T6 — orchestrator-authorised scope extension: fix `test_health.py`, widen CI mypy to match `make lint`

## Orchestrator update (mid-session)

2026-09-25: Orchestrator reports the human approved pushing; `main` and
`phase-p0-p1` are now on `origin` (github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql).
This agent still does not push — finishing and committing locally only. AC1
in `post-dev.md` is worded "Pending — orchestrator verifies after push"
accordingly.
