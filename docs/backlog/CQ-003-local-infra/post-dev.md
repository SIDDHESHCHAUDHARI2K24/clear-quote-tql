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

*(left for the fresh-subagent reviewer)*

## How to test manually

1. `make up` — wait for it to exit 0.
2. Open `http://localhost:8025` (Mailpit) and `http://localhost:8080` (Temporal UI) in a browser — both should load.
3. `docker compose -f infra/docker-compose.yml exec postgres psql -U cq -d cq_dev -c '\l'` — confirm `cq_dev`, `cq_test`, `temporal` are listed.
4. `docker compose -f infra/docker-compose.yml logs minio-init` — confirm the `clear-quote` bucket message and exit code 0 (`docker inspect clear-quote-minio-init-1 --format '{{.State.ExitCode}}'`).
5. `make down` — confirm all `clear-quote-*` containers are gone (`docker ps -a --filter name=clear-quote`); volumes (`docker volume ls | grep clear-quote`) remain.
6. `make up` again — confirm it succeeds a second time from that state.

## Follow-ups

- CQ-004's backend config/env loading should be checked against `.env.example` once written — no changes were needed to `.env.example` in this item, ports/vars already matched.
- If a future Docker Compose upgrade changes `--wait`'s handling of one-shot containers, the `temporal-ui → minio-init` `depends_on` workaround (plan.md Decision #9) can likely be removed; re-test before removing.
