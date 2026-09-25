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
