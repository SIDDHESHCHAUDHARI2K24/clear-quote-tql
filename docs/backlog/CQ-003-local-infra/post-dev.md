# CQ-003 — Post-development notes

## Summary

Added `infra/docker-compose.yml` (project name `clear-quote`) bringing up Postgres, Valkey, MinIO (+ one-shot bucket-init sidecar), Mailpit and Temporal (server + UI) behind the already-pinned `make up`/`make down`/`make logs` targets, plus `infra/postgres/init-databases.sh` so `cq_test` and `temporal` exist alongside the stock `cq_dev` database with zero manual steps. All seven services reach the expected state under `docker compose up -d --wait`, Mailpit and Temporal UI are reachable over HTTP, all three Postgres databases exist, the MinIO bucket is created idempotently, and a `make down && make up` cycle succeeds from a clean state. The stack was left down (containers/network removed, named volumes retained) and the pre-existing `kaneo-evaluation` compose project was left untouched throughout.

## Deviations from spec

| Spec said | Built | Why |
| --- | --- | --- |
| `temporal` env includes `DYNAMIC_CONFIG_FILE_PATH` (implied by common examples referenced in spec's verification note) | Omitted the env var entirely | The path commonly cited (`config/dynamicconfig/development-sql.yaml`) doesn't exist in the current `temporalio/auto-setup:latest` image (it ships only an empty `docker.yaml`); setting it to a missing path crashes the server. See plan.md Decision #8. |
| AC4 command: `psql -U cq -c '\l'` | Ran `psql -U cq -d cq_dev -c '\l'` | `psql -U cq` with no `-d` defaults to database `cq` (doesn't exist by design). Plan.md Decision #10. |
| (implicit) `make up` succeeds as pinned | Added a `depends_on: minio-init: condition: service_completed_successfully` edge from `temporal-ui` to `minio-init` | This Docker Compose version's `--wait` fails on any exited container (even exit 0, `restart: "no"`) unless something declares this exact dependency condition on it. Verified with an isolated repro. Plan.md Decision #9. Purely orchestration; no functional relationship between the two services. |
| Init script mounted at `/docker-entrypoint-initdb.d/` | `infra/postgres/init-databases.sh` uses `psql --dbname "$POSTGRES_DB"` (not shown explicitly in spec) | Same default-database issue as AC4; without `--dbname` the init script itself fails on first boot. Plan.md Decision #11. |

None of these change any pinned service name, image, port, env var name, or Makefile command text — only a config-correctness fix (Temporal), one extra `depends_on` edge (compose-tool-version workaround), and the exact shell invocation used to exercise the two pinned `psql`-based commands.

## Acceptance evidence (stage 7)

| Criterion | Status | Evidence |
| --- | --- | --- |
| AC1 — All services healthy; Temporal UI and Mailpit reachable | Pass | `make up` exits 0 (see Test log); `curl` to both UIs returns `200` (AC3 evidence below serves as the browser-reachability proxy per the brief's "use curl" instruction) |
| AC2 — `docker compose ps` shows every service Up/healthy | Pass | `docker compose -f infra/docker-compose.yml ps` (running services): all six long-running services `Up (healthy)`; `ps -a` additionally shows `minio-init` as `Exited (0)` — the one-shot init container's spec-designed terminal state (AC5), not a failure |
| AC3 — Mailpit (`:8025`) and Temporal UI (`:8080`) both HTTP 200 | Pass | `curl -sf -o /dev/null -w '%{http_code}' http://localhost:8025` → `200`; same for `:8080` → `200` (checked twice, across two separate `make up` runs) |
| AC4 — Postgres has `cq_dev`, `cq_test`, `temporal` | Pass | `docker compose -f infra/docker-compose.yml exec postgres psql -U cq -d cq_dev -c '\l'` lists `cq_dev`, `cq_test`, `postgres`, `template0/1`, `temporal`, and `temporal_visibility` (the last created automatically by Temporal's own auto-setup, not by our init script) |
| AC5 — `clear-quote` bucket exists, `minio-init` exits 0, no manual step | Pass | `docker compose -f infra/docker-compose.yml logs minio-init` → `Added `local` successfully.` / `Bucket created successfully `local/clear-quote`.` / `bucket clear-quote ready`; `docker inspect clear-quote-minio-init-1 --format '{{.State.ExitCode}}'` → `0` |
| AC6 — `make down` stops/removes cleanly; second `make up` succeeds from clean state | Pass | `make down` exit 0, `docker ps -a --filter name=clear-quote` empty afterward; immediate `make up` again exit 0 with all services healthy (see Test log) |

## Test log (stage 5)

| Check | Command | Result |
| --- | --- | --- |
| Port pre-check | `lsof -iTCP -sTCP:LISTEN -P` + `docker ps` | Only 5183/9000/9001 (Kaneo) taken; all 8 needed ports free |
| Compose syntax | `docker compose -f infra/docker-compose.yml config --quiet` | Exit 0, no errors |
| Stack up (clean) | `docker compose -f infra/docker-compose.yml down -v && make up` | Exit 0; all 6 long-running services `Healthy`, `minio-init` `Exited (0)` |
| AC2 | `docker compose -f infra/docker-compose.yml ps` / `ps -a` | 6 services `Up (healthy)`; `minio-init` `Exited (0)` |
| AC3 | `curl -sf -o /dev/null -w '%{http_code}' http://localhost:8025` / `:8080` | `200` / `200` |
| AC4 | `docker compose -f infra/docker-compose.yml exec postgres psql -U cq -d cq_dev -c '\l'` | Lists `cq_dev`, `cq_test`, `temporal` (+ `temporal_visibility`, `postgres`, templates) |
| AC5 | `docker compose -f infra/docker-compose.yml logs minio-init`; `docker inspect … ExitCode` | Bucket created; exit code `0` |
| AC6 | `make down` → `docker ps -a --filter name=clear-quote` (empty) → `make up` | `make down` exit 0; second `make up` exit 0, all healthy again |
| Final state left for reviewer | `make down` (no `-v`); `docker volume ls \| grep clear-quote` | Stack down; `clear-quote_postgres_data`, `clear-quote_minio_data` retained |
| Kaneo isolation | `docker ps --format '{{.Names}}' \| grep kaneo` before/after | `kaneo-evaluation-*` containers (4) present and unaffected throughout |

No `make lint` / `make test` changes apply — this item touches only `infra/` and a `Makefile` comment; the existing backend/frontend lint and test suites are unaffected and were not the subject of this item's changes (CQ-002 already established them green).

## Review findings (stage 6)

Fresh-subagent review (did not write this code). All acceptance criteria re-verified independently by re-running `make up`, the AC-mapped commands, `make down`, a second `make up`, and a final `make down`, plus `make lint` / `uv run pytest backend`. Kaneo isolation checked with `docker ps -a` before and after every cycle.

| # | Severity | file:line | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | minor | `docs/backlog/CQ-003-local-infra/spec.md:64` (AC4) | Confirmed AC4's command as literally written, `docker compose exec postgres psql -U cq -c '\l'`, fails: reproduced independently — `psql: error: … FATAL: database "cq" does not exist` (exit 2). `psql -U cq` with no `-d`/`PGDATABASE` defaults to a database named after the connecting role, which doesn't exist by design (only `cq_dev`, `cq_test`, `temporal` exist). The author correctly diagnosed this (plan.md Decision #10) and ran `psql -U cq -d cq_dev -c '\l'` instead for AC4 evidence, without touching spec.md — correct per AGENTS.md ("do not change … another item's spec.md"). | Whoever next has spec.md edit rights should fix AC4's command in spec.md to `docker compose exec postgres psql -U cq -d cq_dev -c '\l'` so future runs of this item don't re-trip on the same typo. Not a blocker for this branch. |
| 2 | minor | `infra/docker-compose.yml:100-111` | `temporal-ui` declares `depends_on: minio-init: condition: service_completed_successfully` purely to work around this Docker Compose version's `--wait` treating any one-shot/exited container as unhealthy unless something declares that exact condition on it (plan.md Decision #9). The edge is real in the compose graph even though `temporal-ui` has zero functional relationship to `minio-init` — a `docker compose ps`/dependency-graph reader could reasonably infer a real coupling that doesn't exist. It is inline-commented in the compose file and already flagged as a re-test-before-removing follow-up in post-dev.md, so no action is required now. | If a future Compose upgrade removes the need for this (per the existing Follow-ups note), delete the `depends_on` edge then. Alternatively, consider moving `minio-init` outside `--wait`'s purview entirely (e.g. a `make up` step that runs it via `docker compose run --rm minio-init` after the main `up --wait`) to avoid an artificial dependency edge — optional, not blocking. |
| 3 | nit | `infra/docker-compose.yml:79-91` (`temporal`) | Dropping `DYNAMIC_CONFIG_FILE_PATH` (not in the spec's pinned env-var list to begin with) was verified against the actual `temporalio/auto-setup:latest` image contents (empty `docker.yaml`, no `development-sql.yaml`) rather than assumed — sound, no pinned name/port/service changed. No action needed. | — |
| 4 | nit | repo root (worktree) | `make lint`'s `pnpm -r run lint` step fails in this worktree with `eslint: command not found` because `node_modules` isn't installed here (fresh git worktree, no `pnpm install` run). This is a pre-existing/environmental gap unrelated to this diff — CQ-003 touches only `infra/` and one Makefile comment; `uv run ruff check/format`, `uv run mypy backend/app`, and `uv run pytest backend` (the parts of `make lint`/`make test` this item could plausibly affect) all pass clean. Not a CQ-003 finding. | Run `pnpm install` at the repo root before relying on `make lint`'s frontend step in a fresh worktree — no code change needed. |

**CQ-004 reliance check:** `.env.example`'s `DATABASE_URL`/`TEST_DATABASE_URL` (`cq`/`cq`@`localhost:5432`/`cq_dev`|`cq_test`), `VALKEY_URL` (`localhost:6379`), `S3_ENDPOINT`/`S3_BUCKET`/`S3_ACCESS_KEY`/`S3_SECRET_KEY` (`localhost:9010`, `clear-quote`, `cq-minio`/`cq-minio-secret`), and `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE` (`localhost:7233`/`default`) all match this compose file's actual credentials and published ports exactly. Independently confirmed: the `default` Temporal namespace exists and the frontend gRPC service answers over the published `7233` port (verified via `curl http://localhost:8080/api/v1/namespaces` through Temporal UI's proxy, which listed both `temporal-system` and `default`); the `clear-quote` MinIO bucket exists; `cq_dev`/`cq_test`/`temporal` Postgres databases exist. CQ-004's `/health` checks (DB, Valkey, MinIO, Temporal) and its `TEST_DATABASE_URL`-backed pytest fixtures can rely on this stack as-is, no changes needed.

**Verdict: APPROVE.** No critical or major findings — every acceptance criterion re-verified with real commands and matches the evidence already in this file; Kaneo's containers, volumes and ports (5183, 9000, 9001) were confirmed untouched before, during and after every `make up`/`make down` cycle run in this review.

### Commands re-run in this review (all pass)

| Command | Result |
| --- | --- |
| `docker ps -a` (baseline) | 5 `kaneo-evaluation-*` containers present, ports 5183/9000-9001 owned by Kaneo |
| `docker compose -f infra/docker-compose.yml config --quiet` | Exit 0 |
| `make up` (1st) | Exit 0, ~7.3s, all 6 long-running services healthy, `minio-init` exited 0 |
| `docker compose -f infra/docker-compose.yml ps` / `ps -a` | AC2 pass — 6 services `Up (healthy)`, `minio-init` `Exited (0)` |
| `curl -sf -o /dev/null -w '%{http_code}' http://localhost:8025` / `:8080` | AC3 pass — `200` / `200` |
| `docker compose exec postgres psql -U cq -c '\l'` (literal spec command) | Fails as documented above — `FATAL: database "cq" does not exist` |
| `docker compose exec postgres psql -U cq -d cq_dev -c '\l'` | AC4 pass — lists `cq_dev`, `cq_test`, `temporal` (+ `temporal_visibility`, `postgres`, templates) |
| `docker compose logs minio-init` + `docker inspect … ExitCode` | AC5 pass — bucket created, exit code `0` |
| `make down` → `docker ps -a --filter name=clear-quote` (empty) → `make up` (2nd) → `docker compose ps` | AC6 pass — clean teardown, second `make up` exits 0, all healthy again |
| `curl http://localhost:8080/api/v1/namespaces`, `.../cluster-info` | `default` and `temporal-system` namespaces present, cluster info returned — Temporal frontend fully functional, not just port-open |
| `docker ps --format '{{.Names}}\t{{.Ports}}' \| grep kaneo` (after each cycle) | Kaneo's 4 running containers and ports 5183/9000-9001 unchanged throughout |
| `make down` (final, no `-v`) | Exit 0; `clear-quote_postgres_data`/`clear-quote_minio_data` volumes retained; stack left DOWN |
| `uv run ruff check backend` / `ruff format --check backend` / `mypy backend/app` | All pass |
| `uv run pytest backend` | 1 passed (placeholder test; no real backend code yet — CQ-004) |
| `make lint` (`pnpm -r run lint`) | Fails — `eslint: command not found`, missing `node_modules` in this worktree (environmental, unrelated to this diff; see finding #4) |

## How to test manually

1. `make up` — wait for it to exit 0.
2. Open `http://localhost:8025` (Mailpit) and `http://localhost:8080` (Temporal UI) in a browser — both should load.
3. `docker compose -f infra/docker-compose.yml exec postgres psql -U cq -d cq_dev -c '\l'` — confirm `cq_dev`, `cq_test`, `temporal` are listed.
4. `docker compose -f infra/docker-compose.yml logs minio-init` — confirm the `clear-quote` bucket message and exit code 0 (`docker inspect clear-quote-minio-init-1 --format '{{.State.ExitCode}}'`).
5. `make down` — confirm all `clear-quote-*` containers are gone (`docker ps -a --filter name=clear-quote`); volumes (`docker volume ls | grep clear-quote`) remain.
6. `make up` again — confirm it succeeds a second time from that state.

## Follow-ups

- CQ-004's backend config/env loading should be checked against `.env.example` once written — no changes were needed to `.env.example` in this item, ports/vars already matched.
- If a future Docker Compose upgrade changes `--wait`'s handling of one-shot containers, the `temporal-ui → minio-init` `depends_on` workaround (plan.md Decision #9) can likely be removed; re-test before removing. **Done below — see "CI clean-up pass".**

## CI clean-up pass (deferred, 2026-09-25)

Review finding #2 (below) fixed per `docs/backlog/phase-p0-p1-merge-plan.md` gate G3, once Phase 1 was otherwise complete. Plan.md Decisions #12–14 above.

### What changed

- `infra/docker-compose.yml`: removed `temporal-ui`'s artificial `depends_on: minio-init: condition: service_completed_successfully` edge (and its comment). `temporal-ui` now only declares its real dependency, `temporal: condition: service_started`.
- `Makefile`'s `up` target: `docker compose up -d --wait postgres valkey minio mailpit temporal temporal-ui` (the six long-running services named explicitly, `minio-init` excluded) followed by `docker compose run --rm minio-init`. `down`/`logs` untouched.

### Evidence — `make up` against the already-running shared stack

Per the orchestrator's brief, the stack was never stopped/torn down to test this (no `make down`, no cold start). Verified twice against the live shared stack instead, from the `cq-006-ci-cleanup` worktree:

| Run | Command | Result |
| --- | --- | --- |
| 1st `make up` | `make up` (stack already running from earlier work) | Exit 0, ~7.5s. `postgres` showed `Recreate`/`Recreated` — **not caused by this diff**: `postgres`'s service definition is byte-identical to before this change (only `temporal-ui`'s `depends_on` was touched); the recreate reflects the `clear-quote` Compose project being shared, by fixed project name, across several parallel worktrees that each hold their own (occasionally slightly different) copy of `infra/docker-compose.yml` — whichever worktree's `up` runs last reconciles the container to its own file. The other 5 services stayed `Running`. `minio-init` ran via `docker compose run --rm`, printed `Added local successfully` / `Bucket created successfully local/clear-quote` / `bucket clear-quote ready`, and exited 0. |
| 2nd `make up` (immediately after) | `make up` | Exit 0, ~2.1s, **no recreation** — all 6 services stayed `Running`/`Healthy` throughout, confirming the new `up` target is idempotent once every worktree's compose file agrees. `minio-init` ran again via `run --rm`, same success output (bucket already existed, `mc mb --ignore-existing` is a no-op). |
| Health check | `docker compose -f infra/docker-compose.yml ps` | All 6 long-running services `Up`/`healthy`. |
| UI reachability | `curl -sf -o /dev/null -w '%{http_code}' http://localhost:8025` / `:8080` | `200` / `200` |
| Data survived the `postgres` recreate | `docker compose exec postgres psql -U cq -d cq_dev -c '\l'` | Lists `cq_dev`, `cq_test`, `temporal`, `temporal_visibility` (+ two extra DBs from other worktrees' work, `cq_dev_p2`/`cq_test_cq011`/`cq_test_p2` — all on the same named `postgres_data` volume, none touched) |
| Bucket check (independent of `minio-init`'s own logs, since `run --rm` removes its container) | `docker run --rm --network clear-quote_default --entrypoint sh minio/mc:latest -c "mc alias set local http://minio:9000 cq-minio cq-minio-secret >/dev/null && mc ls local/"` | Lists both `clear-quote/` and `clearquote-demo-docs/` (the latter from CQ-010's seed docs) |
| Volumes untouched | `docker volume ls \| grep clear-quote` | `clear-quote_postgres_data`, `clear-quote_minio_data` — both present throughout, never removed |

No `make down` was run at any point in this pass; the shared stack was left running, healthy, for other parallel agents.

### Note for future cross-worktree work

The `postgres` recreate observed above (and already present before this pass started — the container was already at "41 minutes" old on first inspection, versus "3 hours" for its siblings) is a pre-existing consequence of multiple worktrees sharing one fixed Compose project name (`clear-quote`) with independently-edited copies of `infra/docker-compose.yml`. It does not lose data (named volumes persist across container recreation) but is worth knowing about if a shared service unexpectedly restarts during parallel Phase 1/2 work — not a regression introduced by this clean-up pass, and out of scope to "fix" here (it would require every worktree's compose file to be byte-identical, which isn't this item's concern).

## MinIO image follow-up (2026-09-25)

Fixes CQ-006 Decision #17's flagged finding: `minio/minio:latest` and `minio/mc:latest` are gone from Docker Hub/quay.io (MinIO went source-only distribution, ~Oct 2025), breaking `make up` on any fresh clone (merge-plan gate G5). Orchestrator decision: local compose uses the exact same image/tag as CI so the two can't diverge again. See plan.md's "MinIO image follow-up" decisions #15–16.

### What changed

- `infra/docker-compose.yml`: `minio` now runs `bitnamilegacy/minio:2025.5.24-debian-12-r5` (pinned — resolved as the named tag currently sharing `bitnamilegacy/minio:latest`'s digest, via the Docker Hub tags API), with `MINIO_DEFAULT_BUCKETS: "clear-quote,clearquote-demo-docs"` creating both buckets at container start. Data volume changed from `minio_data:/data` to a new `minio_bitnami_data:/bitnami/minio/data` (Bitnami's non-root image can't write into the old volume — see below). `minio-init` service removed entirely (`minio/mc:latest`, also unpullable, no longer needed).
- `Makefile`'s `up` target: drops the `docker compose run --rm minio-init` step; all 6 services are now ordinary `--wait` targets.
- `.github/workflows/ci.yml`: `minio` service image repinned from `bitnamilegacy/minio:latest` to the same exact tag as compose, `2025.5.24-debian-12-r5`.
- `docs/backlog/CQ-003-local-infra/spec.md`: updated the compose table's `minio` row and AC5 (image, bucket-creation mechanism, evidence command) to match; `minio-init` row removed. Scope of the edit limited to those two spots, per the orchestrator's note.

### Permission-denied on the old `minio_data` volume

First `make up` attempt failed: `minio` container exited 1, log `/opt/bitnami/scripts/libminio.sh: line 370: /bitnami/minio/data/.root_user: Permission denied`. Root cause: the existing `clear-quote_minio_data` volume's root directory was written by the old `minio/minio` image, which runs as root; Bitnami's `minio` image runs as a non-root user and can't write into a root-owned volume root. Object data was never going to carry over either way (orchestrator-acknowledged — sample docs are regenerated by `make demo-reset`), so switched to a new volume name (`minio_bitnami_data`) rather than trying to fix permissions on the old one. `minio_data` is still declared in `infra/docker-compose.yml`'s top-level `volumes:` (unused by any service, commented) — the underlying `clear-quote_minio_data` Docker volume was **not removed** (per the brief: never remove volumes other than none). **Follow-up for later cleanup: `docker volume rm clear-quote_minio_data`** once confirmed unneeded (name to remove, not automated here).

### Evidence

| Check | Command | Result |
| --- | --- | --- |
| Tag lookup | `curl -s 'https://hub.docker.com/v2/repositories/bitnamilegacy/minio/tags/latest'` then matched its digest against the tags list | `latest`'s digest (`sha256:451fe685...`) matches named tag `2025.5.24-debian-12-r5` |
| Image pullable | `docker pull bitnamilegacy/minio:2025.5.24-debian-12-r5` | `Status: Downloaded newer image` / `Image is up to date` |
| Compose validates | `docker compose -f infra/docker-compose.yml config` | Exit 0 |
| Fresh-clone proof (no shared-stack changes) | `docker pull` on all 6 images in the compose file (`postgres:16-alpine`, `valkey/valkey:7-alpine`, `bitnamilegacy/minio:2025.5.24-debian-12-r5`, `axllent/mailpit:latest`, `temporalio/auto-setup:latest`, `temporalio/ui:latest`) | All 6 succeed |
| `make up` against the shared stack | `make up` (1st attempt) | `minio` exited 1, `Permission denied` (see above) |
| `make up` after volume-name fix | `make up` | Exit 0; only `minio` recreated (new image + new volume), all 6 services `Healthy` within seconds |
| Buckets exist at boot, no manual step | `docker run --rm --network clear-quote_default --entrypoint sh bitnamilegacy/minio-client:latest -c "mc alias set local http://minio:9000 cq-minio cq-minio-secret && mc ls local/"` | Lists both `clear-quote/` and `clearquote-demo-docs/` |
| `demo-reset` | `SEED_STAFF_PASSWORD=dev-local-test-password uv run python -m seed.reset` | Exit 0, ~1.4s: 4 users, 10 personas, 200 background applications |
| Seed's MinIO document tests | `uv run pytest seed` (CI-shaped env, `INTEGRATION_LATENCY_ENABLED` unset/false) | **23 passed in 8.3s**, including `test_documents_watermarked.py::test_upload_sample_document_key_has_sample_suffix_and_round_trips_via_minio` (the real MinIO round-trip) |
| `make lint` | `make lint` | ruff / ruff format / mypy / eslint / tsc / prettier all pass |
| `make test` | `uv run pytest backend` (247 passed), `uv run pytest seed` (23 passed), `pnpm -r run test` (4/4 workspaces, 35 tests) | All pass |
| `actionlint` | `actionlint .github/workflows/ci.yml` | Exit 0, no output |

### Investigation: `pytest seed` appeared to hang mid-run (not a real bug)

Mid-verification, `uv run pytest seed -v` (run with a local `.env` sourced, created only for this session's manual testing — see below) appeared to stall for 8+ minutes at `test_provider_rows_seeded.py`, with ~0% CPU and two Postgres `cq_test` connections sitting idle (one "idle in transaction" after a `RELEASE SAVEPOINT`, one idle after a completed `COMMIT`). The orchestrator flagged this as a possible connection-pool exhaustion or CI-env divergence and asked for a systematic debug pass before continuing.

**Root cause, confirmed, not a regression from this change:** this worktree had no `.env` file (none is committed; `.env.example` is the template). To run `make demo-reset` for this pass's AC evidence, a `.env` was created by copying `.env.example` — which sets `INTEGRATION_LATENCY_ENABLED=true` (the shipped local-dev default, CQ-009). `seed/tests/conftest.py` only sets that var via `os.environ.setdefault("INTEGRATION_LATENCY_ENABLED", "false")`, which **does not override an already-set environment variable** — so sourcing that `.env` before `pytest` silently flipped every mock adapter call (LOS, tax, rent, STR, credit, insurance, property search, CRM) from instant to a real 200–1200 ms simulated delay, for every one of the ~8–10 tests in `test_provider_rows_seeded.py` that each re-seed all 10 personas from scratch via the function-scoped `seeded_base` fixture. That's the exact risk CQ-010 spec.md Decision D3 already documents for a single `demo-reset` run, multiplied across many independent tests — legitimately slow, not stuck. Postgres's two idle connections were consistent with this: neither had an active query or lock wait (`wait_event_type`/`wait_event` both `Client`/`ClientRead`, meaning "waiting on the client app," not "blocked in Postgres") — confirming the stall was in application code (`asyncio.sleep`), not a DB-side deadlock or pool exhaustion.

Confirmed by re-running the same test file (and then the full `seed` suite) with `env -i` and only the exact CI-shaped env vars (`APP_ENV`, `TEST_DATABASE_URL`, `VALKEY_URL`, `S3_*`, etc. — no `INTEGRATION_LATENCY_ENABLED` override, so the test suite's own `false` default applies): `test_provider_rows_seeded.py` alone passed 8/8 in 4.9s, and the full `seed` suite passed 23/23 in 8.3s — no hang, no pool issue. Fixed the local `.env` (`INTEGRATION_LATENCY_ENABLED=false`, matching how a developer running tests, as opposed to a live dev server, should set it) so this doesn't recur locally. Not a code change — `.env` is git-ignored and never committed; nothing in `seed/`, `backend/app/integrations/`, or this item's MinIO diff was touched to "fix" this.
