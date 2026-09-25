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

## CI clean-up pass (deferred, 2026-09-25) — decisions

Per `docs/backlog/phase-p0-p1-merge-plan.md` gate G3, fixing the two review findings from the round that approved this item, plus wiring `pytest seed` (CQ-010) into CI as G3 requires.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 10 | Decision | Review finding #1 — AC2 evidence was stale | `post-dev.md`'s AC2 row said the `pull_request` trigger was unverified. It has since fired for real: PR #1's run [36098405665](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36098405665) (event `pull_request`, head `phase-p0-p1`). Combined with the original push run [36098019743](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36098019743) (event `push`, branch `cq-006-ci`), both halves of AC2 (`push` on a non-`main` branch, and `pull_request`) are now evidenced by real runs. Updated `post-dev.md`'s AC2 row accordingly. |
| 11 | Decision | Review finding #2 — bump off Node-20 majors | Looked up each action's latest release (`gh api repos/<owner>/<repo>/releases/latest`) and read the changelogs between the pinned and latest majors for breaking input/behavior changes (see below), then bumped: `actions/checkout@v4→v7`, `actions/setup-node@v4→v7`, `actions/cache@v4→v6`, `astral-sh/setup-uv@v3→v10.2.0`. All four now run on the Node 24 runtime, clearing the deprecation annotations. |
| 12 | Decision | `astral-sh/setup-uv` pin format changed at v8 | v8.0.0's release notes: "No more major and minor tags" (supply-chain hardening) — `@v10` does not exist as a ref (confirmed empty `git ls-remote --tags` for `v10`, unlike `checkout`/`setup-node`/`cache` which still publish moving major tags). Pinned the exact release tag `astral-sh/setup-uv@v10.2.0` instead of a moving major. |
| 13 | Decision | `actions/setup-node@v5`'s new automatic pnpm caching | v5 auto-enables its own cache lookup whenever `package.json` has a `packageManager` field (ours does: `"pnpm@9.15.4"`, CQ-002) — before `corepack enable` even runs in this job, so `pnpm` isn't necessarily resolvable yet when setup-node would try. Added `package-manager-cache: false` to keep this job's existing explicit `pnpm store path` + `actions/cache` steps as the only caching path, unchanged behavior. |
| 14 | Decision | Other v5–v7 changes checked, no adaptation needed | `checkout` v6's "persist creds to a separate file" and v7's fork-PR blocking (only applies to `pull_request_target`/`workflow_run`, which this workflow doesn't use) — no impact. `setup-uv` v6's `activate-environment` default change — irrelevant, this workflow never sets `python-version` on the action or relies on an auto-activated venv (`uv run ...` is used throughout). `setup-uv` v9's `prune-cache` default flip to `false` — a cache-size/cost tradeoff, not a correctness break; left at the new default. |
| 15 | Decision | G3 — CI must run `pytest seed` (CQ-010) | Read `seed/tests/*`: everything except `seed/tests/test_documents_watermarked.py` only needs Postgres (already a service container in this job, `cq_test`) and env already set (`APP_ENV`, `SECRET_KEY`→`FIELD_ENCRYPTION_KEY` via `backend/conftest.py`'s `setdefault`, `SEED_STAFF_PASSWORD` via `seed/tests/conftest.py`'s `setdefault`). `test_documents_watermarked.py` does a real MinIO upload/download round-trip via `boto3`/`get_settings()`'s `S3_*` fields — no mocking, by design (AC6 proves a real object exists). Switched the job's `S3_*` env from dummy/unresolvable values to the real MinIO service container's credentials (`cq-minio`/`cq-minio-secret`, matching `infra/docker-compose.yml`) — `VALKEY_URL`/`TEMPORAL_*` stay dummy, untouched (still only exercised via monkeypatching/fakeredis, never `pytest seed` for real). Added `- run: uv run pytest seed` as the job's last backend step, deliberately the same command text as `make test`'s second line, so the two can't drift (per the orchestrator's brief). |
| 16 | Decision | No service-container Postgres change needed for `pytest seed` | `seed/tests/conftest.py`'s `test_engine` fixture reads `get_settings().test_database_url`, already `TEST_DATABASE_URL=postgresql+asyncpg://cq:cq@localhost:5432/cq_test` in this job — the same `postgres:16-alpine` service container `pytest backend` already uses, no new service needed. |
| 17 | Decision — discovered mid-implementation | `minio/minio` (the image `infra/docker-compose.yml` pins) can't be pulled at all any more | First attempt used a plain `docker run` step for MinIO (GitHub Actions `services:` containers can't be given a run command, and `minio/minio`'s default `CMD` doesn't start the server without one). It failed in the real CI run (36115433363, backend job, "Start MinIO" step): `pull access denied for minio/minio, repository does not exist or may require 'docker login'`. Confirmed locally too (`docker pull minio/minio:latest` and `docker pull minio/mc:latest` both fail the same way; `quay.io/minio/minio` also 401s). Web search confirmed: MinIO went source-only distribution and pulled its official images from both Docker Hub and quay.io (removals started ~Oct 2025) — this is not a transient outage. Switched to `bitnamilegacy/minio:latest` (Bitnami's own org, still pullable, confirmed working locally: self-starts from env vars alone — no command needed at all, so it now runs as an ordinary `services:` entry rather than a `docker run` step — and `MINIO_DEFAULT_BUCKETS: "clear-quote,clearquote-demo-docs"` creates both buckets at container start, removing the separate bucket-creation step too). This is **not scoped to CQ-006 alone**: `infra/docker-compose.yml`'s `minio` and `minio-init` (`minio/mc:latest`) services use the same now-unpullable images — harmless today only because they're already cached on every worktree's dev machine, but would break `make up` on any genuinely fresh clone/machine, which is exactly what merge-plan gate G5 ("clean-checkout verification") tests. Flagged to the orchestrator as a new, real, cross-cutting finding rather than silently expanding CQ-003's scope to migrate the local compose file's images too — that's a decision for whoever owns G5/a new backlog item, not a CQ-006 CI-only call. **Follow-up resolved (2026-09-25):** the orchestrator picked this finding up as a `CQ-003: fix: switch MinIO to a pullable image` change — `infra/docker-compose.yml`'s `minio` now runs `bitnamilegacy/minio` (pinned to the exact same tag, `2025.5.24-debian-12-r5`, as this workflow's `minio` service, so the two can't diverge again), `minio-init` is gone (bucket creation moved to `MINIO_DEFAULT_BUCKETS`), and this workflow's `minio:latest` was itself repinned to that same exact tag. See `docs/backlog/CQ-003-local-infra/plan.md`'s "MinIO image follow-up" decisions #15–16 and its `post-dev.md` for full evidence. |
| 18 | Decision (orchestrator-directed) | api-client drift guard + phase-p0-p1 merge | Mid-session, the whole-phase review found CQ-011 added `POST /applications/{id}/pipeline/{start,resume}` without regenerating `packages/api-client` (generated, never hand-edited, per AGENTS.md). Orchestrator asked this branch to: (a) merge the now-updated `phase-p0-p1` (CQ-011 merged) in, (b) run `make api-client` and commit the regenerated files, (c) add a CI job that repeats the generation and fails on any diff. Done: merged cleanly (Makefile auto-merged — my `up` target edit and CQ-011's new `worker` target touch different lines); `make api-client` regenerated `packages/api-client/openapi.json`/`src/schema.d.ts` (122/113 new lines — the two pipeline endpoints), committed separately as `CQ-011: fix: ...` (not a CQ-006 change, so not folded into this item's commit); added a third workflow job, `api-client-drift`, that checks out, syncs both `uv` and `pnpm`, runs `make api-client`, then `git diff --exit-code -- packages/api-client` — cheap dummy env (same shape as `backend`'s original placeholder `S3_*`/`VALKEY_URL`/`TEMPORAL_*` values, since this job only imports `app.main.app` to read its OpenAPI schema, never touches real infra). |

Verified locally end to end (this worktree, against the shared `clear-quote` stack's real Postgres/MinIO, with the job's exact env var values, after merging `phase-p0-p1`): `uv run pytest backend` (247 passed, up from 214 pre-merge), `uv run pytest seed` (23 passed), `make lint` and `make test` both green from repo root, `make api-client` idempotent (no further diff on a second run once committed). See `post-dev.md`'s "CI clean-up pass" section for full evidence and the real CI run once repushed.
