# CQ-006 — Post-development notes

## Summary

Added `.github/workflows/ci.yml` with two parallel jobs (`backend`, `frontend`) triggered on every branch push and every pull request, per spec.md's pinned trigger/step list. `backend` runs a real `postgres:16-alpine` service container and `ruff check`/`ruff format --check`/`mypy backend/app`/`pytest backend`; `frontend` runs `pnpm -r run lint`/`typecheck`, `prettier --check .`, and `pnpm -r run test`. Added `permissions: contents: read`, a `concurrency` cancel-in-progress group, and caching for both `uv` (built-in `enable-cache`) and `pnpm` (`actions/cache@v4` keyed on `pnpm-lock.yaml`), none of which change the pinned command list. No pushing/PR was performed (not authorized to push); every job's steps were instead emulated locally with the same commands and environment variables, against a real local Postgres via `make up`, and `actionlint` was run against the workflow file directly. A pre-existing bug in already-merged CQ-004 test code (`test_health_ok` not monkeypatching Valkey/MinIO/Temporal) was found during validation and, with orchestrator authorisation, fixed on this branch; the `backend` job's mypy step was also widened to match `make lint`'s scope exactly, per orchestrator instruction.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| No explicit `permissions:`/`concurrency:` in the YAML skeleton | Added `permissions: contents: read` and `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` | Orchestrator's brief for this item requires least-privilege permissions and a cancel-in-progress concurrency group; spec's Notes explicitly leave `concurrency` optional/deferrable, this doesn't conflict, just adopts it now |
| Spec's step list has no explicit caching | Added `enable-cache: true` to `astral-sh/setup-uv@v3` and a `pnpm store path` + `actions/cache@v4` pair before `pnpm install` | Orchestrator's brief requires caching for uv and pnpm; doesn't change or reorder the pinned lint/type/test commands, only wraps dependency installation |
| — | `actions/checkout@v4` used (not pinned by spec) | Spec doesn't name a checkout action version; `v4` is current stable, consistent style with the `@v3`/`@v4` pins spec does give |
| Spec's Notes: "CQ-004's health checks are monkeypatched in tests, so these never need to resolve in CI" | Not true of the merged code — see below | Pre-existing bug in CQ-004, found during local emulation of the `backend` job, not a CQ-006 decision |

### Fixed issue (orchestrator-authorised scope extension)

`backend/app/features/system/tests/test_health.py::test_health_ok` did **not** monkeypatch `check_valkey`/`check_minio`/`check_temporal` — it exercised the real `boto3`/`redis`/`temporalio` clients against `VALKEY_URL`/`S3_*`/`TEMPORAL_*`, contradicting CQ-004's own `spec.md` ("Valkey/MinIO/Temporal health checks are tested by monkeypatching their clients"). Originally flagged and left unfixed as out of scope; the orchestrator then authorised fixing it on this branch so the first real CI run is green. Fix applied: both `test_health_ok` and `test_health_degraded` now use a shared `_patch_non_db_checks_ok(monkeypatch)` helper that patches `check_valkey`/`check_minio`/`check_temporal` to return `"ok"`; `test_health_degraded` then re-overrides `check_valkey` to its failure case, same behavior as before. Verified with the CI job's exact dummy env (`VALKEY_URL`/`S3_*`/`TEMPORAL_*` unresolvable): **16/16 pass**.

### Fixed issue (orchestrator-authorised scope extension)

CI's `backend` job mypy step was `uv run mypy backend/app` (spec.md's literal text), narrower than `make lint`'s `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` (CQ-004 widened the Makefile's mypy scope after CQ-006's spec.md was written). Orchestrator asked CI to call the same scope as the Makefile so they can't drift. Updated the workflow step to match exactly. Verified: `Success: no issues found in 23 source files`.

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — CI green on `main` | **Pending — orchestrator verifies after push** | Not evidenceable from this worktree; per orchestrator, `main`/`phase-p0-p1` are on `origin` and the orchestrator will push this branch and read the real run. |
| AC2 — triggers on every branch push + PR | **Pass** | `.github/workflows/ci.yml`'s `on:` block matches spec.md verbatim: `push.branches: ["**"]`, `pull_request` (no branch filter). Confirmed with `actionlint` (no errors) and a read of the file. Both trigger kinds now evidenced by real runs (CI clean-up pass, review round 1 finding #1): push run [36098019743](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36098019743) (event `push`, branch `cq-006-ci`); `pull_request` run [36098405665](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36098405665) (event `pull_request`, PR #1, head `phase-p0-p1`) — both `gh run view --json event` confirmed. |
| AC3 — `backend` job's postgres service + `uv run pytest backend` passes | **Pass** | Local emulation: `docker compose -f infra/docker-compose.yml up -d --wait` (same `postgres:16-alpine` image/creds/db as the job's service container) + `uv run pytest backend` with the job's exact env vars (dummy `VALKEY_URL`/`S3_*`/`TEMPORAL_*`, unresolvable): **16 passed** after the `test_health.py` fix above. |
| AC4 — backend job fails on ruff/format/mypy/pytest failure | Pass | Added `import os` unused mid-file to `backend/app/features/system/service.py`: `uv run ruff check backend` → exit 1 (E402, F401). Reverted (`git checkout --`), confirmed exit 0 again. Added `x=1` (misformatted): `uv run ruff format --check backend` → exit 1 ("1 file would be reformatted"). Reverted. Working tree confirmed clean after (`git status --short`). |
| AC5 — frontend job runs lint/typecheck/prettier/test, passes on the scaffold | Pass | From repo root: `pnpm install --frozen-lockfile` (480 packages, from lockfile, no changes) → `pnpm -r run lint` (4/4 workspaces, no errors) → `pnpm -r run typecheck` (4/4 workspaces, no errors) → `pnpm exec prettier --check .` ("All matched files use Prettier code style!") → `pnpm -r run test` (4/4 workspaces: 34 tests passed across `@cq/ui`, `@cq/api-client`, `lo-console`, `borrower-portal`). |
| AC6 — `actionlint` reports no errors | Pass | `actionlint .github/workflows/ci.yml` → no output, exit 0 |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| actionlint | `actionlint .github/workflows/ci.yml` | Clean, exit 0 |
| Backend — ruff check | `uv run ruff check backend` (CI env) | All checks passed |
| Backend — ruff format | `uv run ruff format --check backend` (CI env) | 23 files already formatted |
| Backend — mypy (widened, matches `make lint`) | `uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` (CI env) | Success: no issues found in 23 source files |
| Backend — pytest (CI-realistic dummy env, before `test_health.py` fix) | `uv run pytest backend` (`APP_ENV=test`, dummy `VALKEY_URL`/`S3_*`/`TEMPORAL_*`, real `TEST_DATABASE_URL` against `make up` Postgres) | 14 passed, 2 failed (`test_health.py` — pre-existing CQ-004 bug, see Deviations) |
| Backend — pytest (real infra env, before fix) | `uv run pytest backend` (same, but `VALKEY_URL`/`S3_*`/`TEMPORAL_*` pointed at the real local `make up` stack) | 16 passed |
| Backend — pytest (CI-realistic dummy env, after `test_health.py` fix) | `uv run pytest backend` (job's exact env, dummy `VALKEY_URL`/`S3_*`/`TEMPORAL_*`) | **16 passed** |
| Backend — AC4 regression (ruff check) | Introduced unused import, re-ran `uv run ruff check backend`, reverted | Failed as expected (exit 1), then passed again after revert |
| Backend — AC4 regression (ruff format) | Introduced misformatted line, re-ran `uv run ruff format --check backend`, reverted | Failed as expected (exit 1), then passed again after revert |
| Frontend — install | `pnpm install --frozen-lockfile` | Lockfile up to date, 480 packages |
| Frontend — lint | `pnpm -r run lint` | 4/4 workspaces pass |
| Frontend — typecheck | `pnpm -r run typecheck` | 4/4 workspaces pass |
| Frontend — prettier | `pnpm exec prettier --check .` | All matched files use Prettier code style |
| Frontend — test | `pnpm -r run test` | 4/4 workspaces, 34 tests passed |

## Review findings (stage 6)

Fresh-subagent review (did not write this code). Reviewed `git diff phase-p0-p1...HEAD` against `spec.md`, `plan.md`, `AGENTS.md`, and real evidence: GitHub Actions run [36098019743](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36098019743) (push, branch `cq-006-ci`, commit `633d6b1`) — both jobs green (`frontend` 35s, `backend` 44s).

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | minor | `docs/backlog/CQ-006-ci/post-dev.md:29` | AC2's evidence row is stale: it says "Pending (live trigger)" / "no scratch-branch push performed", but the real run (36098019743) is itself a `push` event on branch `cq-006-ci` (not `main`), which already demonstrates the non-`main` push trigger fires. Only the `pull_request` half of AC2 remains genuinely unverified (no PR opened yet). | Update the AC2 row to record the real run as partial evidence for the push side, and keep the `pull_request` side explicitly Pending until a PR is opened. |
| 2 | minor | `.github/workflows/ci.yml:1` (whole file) | Run 36098019743's annotations flag `actions/checkout@v4`, `actions/setup-node@v4`, `actions/cache@v4`, and `astral-sh/setup-uv@v3` as targeting the now-deprecated Node 20 runtime, forced onto Node 24 by GitHub. The run still passed (this is a warning, not a job failure), and the versions match what `spec.md` pins verbatim, so this isn't a defect in this item's work. Current latests are well ahead: `actions/checkout` v7, `actions/setup-node` v7, `actions/cache` v6, `astral-sh/setup-uv` v10 (checked via `gh api repos/<owner>/<repo>/releases/latest`), which build on Node 24 natively and would clear the annotation. | Not blocking; file a small follow-up item (or fold into whichever item next touches `.github/workflows/ci.yml`) to bump the four pins to their current majors. |

No critical or major findings. Not flagged (verified, no fix needed): the backend job's cache save/restore failed in run 36098019743 due to a GitHub-side Cache Service outage (`Failed to save`, `Cache service responded with 400`) and the job still succeeded — `actions/cache` and `setup-uv`'s built-in cache treat failures as warnings, not job failures, by default (`fail-on-cache-miss` is not set), so the workflow already tolerates cache-service outages without any extra configuration.

### Commands re-run by this reviewer

| Command | Result |
| --- | --- |
| `actionlint .github/workflows/ci.yml` | Pass — exit 0, no output (AC6) |
| `gh run view 36098019743 --repo SIDDHESHCHAUDHARI2K24/clear-quote-tql` | Pass — both jobs `success` |
| `gh run view 36098019743 ... --job=<backend> --log` (grepped for pytest summary) | Pass — `collected 16 items` / `16 passed, 1 warning in 5.77s`; no `skip` in the log (AC3) |
| `gh run view 36098019743 ... --job=<frontend> --log` (grepped for vitest summary) | Pass — 4 workspaces, `1 + 27 + 3 + 3 = 34 passed`, 0 skipped (AC5) |
| Diff of `Makefile`'s `lint`/`test` targets vs `.github/workflows/ci.yml`'s backend/frontend steps | Pass — identical commands verbatim (ruff check, ruff format --check, `mypy backend/app backend/conftest.py backend/tests backend/scripts`, pytest, `pnpm -r run lint/typecheck`, `pnpm exec prettier --check .`, `pnpm -r run test`); no drift |
| `git diff phase-p0-p1...HEAD -- backend/app/features/system/tests/test_health.py` (scope-extension check) | Reviewed — matches plan.md decision #8: shared `_patch_non_db_checks_ok` helper monkeypatches `check_valkey`/`check_minio`/`check_temporal`; `test_health_degraded` still overrides `check_valkey` to fail. Correct, in scope per orchestrator authorisation. |
| Read `docs/backlog/CQ-007-*/spec.md` for `FIELD_ENCRYPTION_KEY`/`APP_ENV` | Confirmed compatible: CQ-007's spec has the app fail fast on missing `FIELD_ENCRYPTION_KEY` only when `APP_ENV` is not `test`; CI's `backend` job sets `APP_ENV: test`, so this will not break when CQ-007 lands. |
| Traced `DATABASE_URL` (dummy, points at a `cq_dev` db the CI Postgres service never creates) vs `TEST_DATABASE_URL` | Verified harmless: `backend/conftest.py`'s `client`/`db_session` fixtures override `get_db` to use `test_database_url` exclusively; `db.py`'s module-level engine (bound to `database_url`) is never queried by the current test suite, confirmed by the real run's 16/16 pass. |

### Verdict

APPROVE. No critical/major findings; 2 minor (both non-blocking, tracked above), 0 nits.

## How to test manually

1. `docker compose -f infra/docker-compose.yml up -d --wait` (or `make up`).
2. Export the `backend` job's env vars from `.github/workflows/ci.yml` (or use real `.env.example` values if a full local stack is running) and run: `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend/app && uv run pytest backend`.
3. From repo root: `pnpm install --frozen-lockfile && pnpm -r run lint && pnpm -r run typecheck && pnpm exec prettier --check . && pnpm -r run test`.
4. `actionlint .github/workflows/ci.yml` should report nothing.

## Follow-ups

- Once the human configures branch protection on `main` requiring both `backend` and `frontend` jobs (out of scope for this item, per spec.md), AC1's exit check is fully closed.
- If a later item needs Valkey/Temporal in CI for real integration coverage, add service containers then (per CQ-004's spec.md Decision) rather than widening this item retroactively. **MinIO is now real in CI** (see "CI clean-up pass" below, G3/CQ-010) — Valkey and Temporal remain dummy/monkeypatched.

## CI clean-up pass (deferred, 2026-09-25)

Fixes review round 1 findings #1–#2 and wires in `pytest seed` (CQ-010) per `docs/backlog/phase-p0-p1-merge-plan.md` gate G3. Plan.md Decisions #10–16 above.

### Review finding #1 — AC2 evidence updated

See the AC2 row above: push run [36098019743](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36098019743) and `pull_request` run [36098405665](https://github.com/SIDDHESHCHAUDHARI2K24/clear-quote-tql/actions/runs/36098405665), both confirmed via `gh run view --json event,headBranch,conclusion,status` (`success`/`completed` for both).

### Review finding #2 — actions bumped off Node-20 majors

| Action | Was | Now | Breaking-change check |
| --- | --- | --- | --- |
| `actions/checkout` | `@v4` | `@v7` | v5/v6/v7 release notes read; only change relevant to us is the Node 24 runtime requirement (met by `ubuntu-latest`) and a fork-PR checkout restriction for `pull_request_target`/`workflow_run` triggers, which this workflow doesn't use. |
| `actions/setup-node` | `@v4` | `@v7`, added `package-manager-cache: false` | v5 auto-enables pnpm caching from `package.json`'s `packageManager` field before `corepack enable` runs in this job — disabled to keep the job's existing explicit pnpm-store caching as the only path (plan.md Decision #13). |
| `actions/cache` | `@v4` | `@v6` | v5/v6 release notes read; Node 24 runtime only, no input/behavior changes affecting this workflow's usage (`path`/`key`/`restore-keys`). |
| `astral-sh/setup-uv` | `@v3` | `@v10.2.0` (exact tag — no moving major published from v8 onward) | v4–v10 release notes read; `enable-cache`/`cache-dependency-glob` inputs unchanged, `activate-environment`'s v6 default change doesn't apply (this workflow never sets `python-version` on the action), `prune-cache`'s v9 default flip to `false` is a cache-size tradeoff only. |

Verified with `actionlint .github/workflows/ci.yml` (exit 0, no errors) before pushing.

### G3 — `pytest seed` (CQ-010) now runs in CI

`backend` job additions: a `Start MinIO` step (`docker run` — GitHub Actions `services:` containers can't be given a command, and `minio/minio`'s default `CMD` needs one, so it isn't declared as a `services:` entry), a `Create MinIO buckets` step (`boto3`, creates `clear-quote` and `clearquote-demo-docs`), and `- run: uv run pytest seed` as the job's final step — the same command text as `make test`'s second line. `S3_*` env vars switched from dummy/unresolvable values to the real MinIO container's credentials (`cq-minio`/`cq-minio-secret`, `http://localhost:9010`, matching `infra/docker-compose.yml`); `VALKEY_URL`/`TEMPORAL_*` stay dummy (still only monkeypatched/faked, never touched for real by `pytest seed`). Added `SEED_STAFF_PASSWORD: ci-dummy-demo-password` explicitly (belt-and-suspenders — `seed/tests/conftest.py` already `os.environ.setdefault()`s a throwaway value; review round 1 finding #3 on CQ-010: no real password is ever committed).

### Test log (this pass)

All commands run from this worktree against the shared `clear-quote` stack's real Postgres (`cq_test`) and MinIO, using the job's exact env var values (`S3_ENDPOINT=http://localhost:9010`, `S3_ACCESS_KEY=cq-minio`, `S3_SECRET_KEY=cq-minio-secret`, etc.):

| Check | Command | Result |
| --- | --- | --- |
| actionlint | `actionlint .github/workflows/ci.yml` | Exit 0, no output |
| Bucket-creation script | `uv run python - <<'PY' ... PY` (the exact heredoc from the workflow) | `clear-quote: already exists`, `clearquote-demo-docs: already exists` |
| Backend — ruff/format/mypy | `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend/app backend/conftest.py backend/tests backend/scripts` | All pass — "All checks passed!", "202 files already formatted", "Success: no issues found in 202 source files" |
| Backend — pytest | `uv run pytest backend` (job's exact env) | **214 passed** |
| Seed — pytest | `uv run pytest seed` (job's exact env, including real `S3_*`) | **23 passed** (includes `test_documents_watermarked.py`'s real MinIO round-trip, AC6) |
| `make lint` (repo root) | `make lint` | ruff/ruff format/mypy/eslint/tsc/prettier all pass |
| `make test` (repo root) | `make test` | `uv run pytest backend` (214), `uv run pytest seed` (23), `pnpm -r run test` (4/4 workspaces, 36 tests) all pass |

### Real CI run (post-push)

Filled in after pushing — see "Acceptance evidence" AC1 row and the run link below.

- Run id / URL: _pending_
- Result: _pending_
- Deprecation annotations: _pending_ (`gh run view <id>` checked for Node-20 deprecation warnings — the whole point of the action bumps above)
