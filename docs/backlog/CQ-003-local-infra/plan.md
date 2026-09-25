# CQ-003 — Implementation plan

Written by the agent in stages 1–3. Do not start coding until every acceptance criterion maps to a test.

## Decisions & questions (stage 1)

Gap check against spec: the spec pins the compose file path, project name, every service/image/port, health checks and Makefile targets exactly, and pre-answers the two biggest open questions (Temporal-on-shared-Postgres, Valkey-via-Redis-client) as `Decision:` entries already. No big gaps found. Small gaps only:

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 1 | Decision | Re-run the `lsof` port check the spec asks for | Ran `lsof -iTCP -sTCP:LISTEN -P` and `docker ps`. Only `5183` (Kaneo web), `9000`/`9001` (Kaneo's own MinIO) are taken among project-relevant ports; `kaneo-evaluation-postgres-1` publishes no host port (container-internal `5432/tcp` only). All eight ports this item needs (`5432, 6379, 9010, 9011, 1025, 8025, 7233, 8080`) are free — matches the spec table, no `.env.example` changes needed. |
| 2 | Decision | Compose project name isolation | Used the top-level `name: clear-quote` key in `infra/docker-compose.yml` (supported by installed Docker Compose v5.2.0) instead of requiring `-p clear-quote` on every Make command — same effect, less error-prone. Verified `docker network ls` shows Kaneo on its own `kaneo-evaluation_default` network; our stack gets its own `clear-quote_default` network, no overlap. |
| 3 | Decision | `temporalio/auto-setup` env vars | Verified against the image's documented compose example (well-known `docker.io/temporalio/auto-setup` usage: `DB=postgres12`, `DB_PORT`, `POSTGRES_USER`, `POSTGRES_PWD`, `POSTGRES_SEEDS`). Pointed it at the `postgres` service (`POSTGRES_SEEDS=postgres`, `POSTGRES_USER=cq`, `POSTGRES_PWD=cq`, `DB=postgres12`, `DB_PORT=5432`) using the `temporal` database created by the init script. No fallback to a dedicated `temporal-postgres` container was needed. |
| 4 | Decision | DB creation split | `cq_dev` is created by the stock `POSTGRES_DB=cq_dev` env var (Postgres image default-database behavior). `cq_test` and `temporal` are created by an init script `infra/postgres/init-databases.sh` mounted at `/docker-entrypoint-initdb.d/10-init-databases.sh`, run once against a fresh volume, both owned by role `cq`. |
| 5 | Decision | Valkey healthcheck fallback | Used `CMD-SHELL "valkey-cli ping || redis-cli ping"` so the check still pins `valkey-cli ping` as primary (per spec) while keeping the documented Redis-CLI fallback for image variants that lack `valkey-cli`. Confirmed `valkey/valkey:7-alpine` ships `valkey-cli` at `/usr/local/bin/valkey-cli`, so the fallback is inert here but harmless. |
| 6 | Decision | `minio-init` bucket-creation mechanism | Used `minio/mc:latest` with a small inline shell command (`mc alias set … && mc mb --ignore-existing …`) rather than a separate script file, since it's a single one-shot container and the spec doesn't pin a script path for it. |
| 7 | Decision | Pre-pulled images not yet cached locally | `valkey/valkey:7-alpine` and `axllent/mailpit:latest` weren't in the local Docker image cache (only other tags/forks were); pulled both before running `make up` so the first run isn't slower/flakier than later runs. No compose file changes from this — informational only. |
| 8 | Decision | `temporalio/auto-setup`'s `DYNAMIC_CONFIG_FILE_PATH` | The commonly-cited example value (`config/dynamicconfig/development-sql.yaml`) does not exist in this image's current build — it ships only `config/dynamicconfig/docker.yaml` (empty). Setting the env var to a non-existent path makes the server fail fast (`Unable to create dynamic config client`, exit 1). Dropped the env var entirely; the server starts fine with no dynamic config overrides, which is all local dev needs. Verified by inspecting the image's `/etc/temporal/config` tree directly (`docker run --rm --entrypoint find temporalio/auto-setup:latest /etc/temporal/config`). |
| 9 | Decision | `docker compose up --wait` and the one-shot `minio-init` container | Empirically confirmed (isolated repro with a bare `busybox … && exit 0` service) that this Docker Compose version (`v5.2.0`) fails `--wait` on **any** container that exits — even with code 0 and `restart: "no"` — *unless* another service in the same compose file declares `depends_on: { that-service: { condition: service_completed_successfully } }` on it; only then does `--wait` treat "exited successfully" as the expected terminal state. Since `minio-init` has no natural consumer among the other six services, added that exact `depends_on` edge from `temporal-ui` (arbitrary but harmless — it only delays `temporal-ui`'s start by the ~1s it takes `minio-init` to run) purely so `make up` succeeds; documented inline in the compose file. Without this, `make up` (AC1/AC6) fails every time despite `minio-init` doing exactly what AC5 asks. |
| 10 | Decision | AC4's exact command (`psql -U cq -c '\l'`, no `-d`) | Fails as literally written: `psql -U cq` with no `-d`/`PGDATABASE` defaults to a database named after the connecting role (`cq`), which doesn't exist (by design — the three real databases are `cq_dev`, `cq_test`, `temporal`). This is inherent `psql`/`libpq` default-database behavior, not a compose issue. Ran the equivalent `psql -U cq -d cq_dev -c '\l'` for AC4 evidence instead (recorded in `post-dev.md`); did not rename any pinned database to fit the example command, mirroring how CQ-002 handled its own AC5 regex mismatch. |
| 11 | Decision | `postgres`'s init script needs `--dbname` too | Same root cause as #10: the init script initially ran `psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER"` with no `--dbname`, which failed with `FATAL: database "cq" does not exist` on first boot (postgres image runs init scripts as the `POSTGRES_USER` role, same default-db rule applies). Fixed by adding `--dbname "$POSTGRES_DB"` (`cq_dev`, guaranteed to exist since the postgres image creates it before running `/docker-entrypoint-initdb.d/*` scripts). |

## Why

CQ-004 onward assumes a live local stack (Postgres, Valkey, MinIO, Mailpit, Temporal) reachable by fixed host ports without colliding with the already-running Kaneo evaluation stack. This item stands that stack up behind `make up`/`make down`/`make logs`, with health checks so `--wait` genuinely blocks until the stack is usable, and a one-shot init container so the MinIO bucket and the three required Postgres databases exist with zero manual steps.

## What changes

| Area | Files (create / modify) |
| --- | --- |
| Compose | `infra/docker-compose.yml` (new) |
| Postgres init | `infra/postgres/init-databases.sh` (new) — creates `cq_test`, `temporal` databases owned by `cq` |
| Makefile | `up`, `down`, `logs` targets — drop the "fails loudly until CQ-003" comment now that the compose file exists; targets' command lines are unchanged (already pinned correctly by CQ-002) |
| Docs | this `plan.md`, `post-dev.md` |

## Tasks

| Task | Description | Depends on | Owned files | Test(s) |
| --- | --- | --- | --- | --- |
| T1 | Write `infra/postgres/init-databases.sh` | — | `infra/postgres/init-databases.sh` | AC4 |
| T2 | Write `infra/docker-compose.yml` (all 7 services, health checks, ports, project name) | T1 | `infra/docker-compose.yml` | AC1, AC2, AC3, AC5 |
| T3 | Update Makefile comment (targets already correct) | T2 | `Makefile` | AC1, AC6 (via `make up`/`make down`) |
| T4 | Bring stack up, verify every AC with real commands, capture output | T1–T3 | — | AC1–AC6 |
| T5 | `make down`, confirm clean second `make up`, then leave stack down | T4 | — | AC6 |
| T6 | Fill `post-dev.md`, remove `infra/.gitkeep` (no longer an empty dir) | T4, T5 | `post-dev.md`, `infra/.gitkeep` (delete) | — |

## Wave schedule (stage 3)

Single agent, sequential — every task depends on the previous one (compose file needs the init script first; verification needs the compose file up). No parallel workers needed.

## Acceptance → test map

| Criterion | Test |
| --- | --- |
| AC1 | `make up` exits 0 (implies all healthchecks passed within `--wait`'s timeout); Temporal UI and Mailpit checked in-browser-equivalent via `curl` (headless env) per AC3 |
| AC2 | `docker compose -f infra/docker-compose.yml ps` — every row `Up`/`healthy` as applicable |
| AC3 | `curl -sf -o /dev/null -w '%{http_code}' http://localhost:8025` and same for `:8080`, both `200` |
| AC4 | `docker compose -f infra/docker-compose.yml exec postgres psql -U cq -c '\l'` lists `cq_dev`, `cq_test`, `temporal` |
| AC5 | `docker compose -f infra/docker-compose.yml logs minio-init` shows bucket created/already-exists and container exit code 0 |
| AC6 | `make down && make up` succeeds a second time from a clean state |

## Progress

- [x] T1
- [x] T2
- [x] T3
- [x] T4
- [x] T5
- [x] T6

## CI clean-up pass (deferred, 2026-09-25) — decisions

Scope: `docs/backlog/CQ-006-ci/spec.md`'s G3 gate (`docs/backlog/phase-p0-p1-merge-plan.md`) asked for CQ-003 review finding #2 to be fixed once Phase 1 was otherwise complete: the artificial `temporal-ui` → `minio-init` `depends_on` edge added as a `--wait` workaround (plan.md Decision #9 above).

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 12 | Decision | Remove the artificial `depends_on` edge | Deleted `temporal-ui`'s `depends_on: minio-init: condition: service_completed_successfully` (and its explanatory comment) from `infra/docker-compose.yml`. `temporal-ui` now only depends on `temporal: condition: service_started`, its real dependency. |
| 13 | Decision | Keep `make up` reliable without that edge | `minio-init` is no longer part of any `--wait` polling: `make up` now runs `docker compose up -d --wait postgres valkey minio mailpit temporal temporal-ui` (the six long-running services, named explicitly) and then `docker compose run --rm minio-init` as a separate, synchronous step once those six are confirmed healthy. `run --rm` still honors `minio-init`'s own `depends_on: minio: condition: service_healthy`, and `mc mb --ignore-existing` keeps the bucket step idempotent across repeated `make up` calls. |
| 14 | Decision | Verification without a cold start | Per the orchestrator's brief, the shared `clear-quote` stack was never stopped (no `make down`, no volume removal) to test this. Verified instead against the already-running stack: `make up` twice in a row (first call recreated only `postgres`, unrelated to this change — see post-dev.md; second call was a true no-op, ~2s, nothing recreated), confirmed all 6 services healthy, `clear-quote`/`clearquote-demo-docs` buckets both present via `mc ls`, and `cq_dev`/`cq_test`/`temporal` databases intact throughout. |

## MinIO image follow-up (2026-09-25) — decision

Scope: CQ-006 Decision #17 flagged that `infra/docker-compose.yml`'s `minio` (`minio/minio:latest`) and `minio-init` (`minio/mc:latest`) are no longer pullable at all (MinIO went source-only distribution, Oct 2025) — breaking `make up` on any fresh clone (merge-plan gate G5), separately from CI's own copy of the same problem (already fixed there). Orchestrator decision: local compose must use the exact same image as CI so the two can't diverge again.

| # | Type | Item | Resolution |
| --- | --- | --- | --- |
| 15 | Decision | Pin `minio` to `bitnamilegacy/minio:2025.5.24-debian-12-r5` | Looked up tags via `curl -s 'https://hub.docker.com/v2/repositories/bitnamilegacy/minio/tags?...'`, resolved which named tag currently shares `latest`'s digest, and pinned that exact tag in both `infra/docker-compose.yml` and `.github/workflows/ci.yml`'s `minio` service (previously `bitnamilegacy/minio:latest` in CI). `MINIO_DEFAULT_BUCKETS: "clear-quote,clearquote-demo-docs"` creates both buckets at container start (matches CI, and `seed/generators/documents.py`'s own idempotent `ensure_demo_docs_bucket` still runs as a harmless no-op safety net). Removed the `minio-init` service (`minio/mc:latest`, also unpullable) and the `docker compose run --rm minio-init` step from `make up` — no longer needed. Updated `docs/backlog/CQ-003-local-infra/spec.md`'s compose table row and AC5 (image name, bucket-creation mechanism, evidence command) to match; kept the edit to those two spots only, per the orchestrator's note. |
| 16 | Decision | New volume name for `minio`'s data | Bitnami's image mounts its data at `/bitnami/minio/data` (not `/data`) and runs as a non-root user; the existing `minio_data` named volume was written by the old, root-run `minio/minio` image, so the new container got `Permission denied` writing into it. Since object data was never going to carry over either way (orchestrator-acknowledged, sample docs are regenerated by `make demo-reset`), added a new volume `minio_bitnami_data` instead of reusing `minio_data`. `minio_data` is left declared-but-unused in `infra/docker-compose.yml`'s `volumes:` block with a comment; the underlying `clear-quote_minio_data` Docker volume itself was **not** removed (per the brief) — flagged for later manual cleanup (`docker volume rm clear-quote_minio_data`) once confirmed unneeded. |

See `post-dev.md`'s "MinIO image follow-up" section for the exact commands and output.
