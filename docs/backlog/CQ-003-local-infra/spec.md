# CQ-003 Local infrastructure

| Field | Value |
| --- | --- |
| Phase | P0 Foundations |
| Depends on | CQ-002 |
| Kaneo task | CQ-003 in Kaneo (task id `r9ygdvtsayxcsp57x2ax0tit`) |
| Branch | `cq-003-local-infra` |
| Status | Ready — filled from design docs on 2026-09-24 |

## Goal

`make up` brings up every backing service the backend needs (Postgres, Valkey, MinIO, Mailpit, Temporal) with one command, on ports that don't collide with anything else on a dev machine, so CQ-004 onward can assume a live stack.

## Scope

Docker Compose: Postgres, Valkey, MinIO + bucket init, Mailpit, Temporal server + UI; `make up`, `make down`, `make logs`.

## Out of scope

- The FastAPI app and Temporal worker themselves (CQ-004, CQ-011) — they run on the host via `uv run`, not as compose services.
- Alembic migrations (CQ-007) — this item only ensures Postgres is reachable and has the right databases.
- Railway/production infra (CQ-035).

## References

- `docs/design/system-design.md` — "Architecture" (stack decisions, diagram), Decisions log #7, #12.
- `docs/design/data-field-catalog.md` — not applicable.
- `AGENTS.md` — Commands table (`make up/down/logs`).

## Compose file & service names (pin exactly)

`infra/docker-compose.yml`, project name `clear-quote`. Services:

| Service name | Image | Host port(s) | Purpose |
| --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | `5432:5432` | App DB (`cq_dev`, `cq_test`) + Temporal's DB (`temporal`) |
| `valkey` | `valkey/valkey:7-alpine` | `6379:6379` | OTP rate limits, short-lived caches |
| `minio` | `bitnamilegacy/minio:2025.5.24-debian-12-r5` (was `minio/minio:latest`, no longer pullable — see post-dev.md "CI clean-up pass" and its follow-up fix) | `9010:9000` (S3 API), `9011:9001` (console) | File storage; creates both `clear-quote` and `clearquote-demo-docs` buckets at startup via `MINIO_DEFAULT_BUCKETS` |
| `mailpit` | `axllent/mailpit:latest` | `1025:1025` (SMTP), `8025:8025` (web UI) | Captures outbound email |
| `temporal` | `temporalio/auto-setup:latest` | `7233:7233` (frontend gRPC) | Workflow engine, backed by the `postgres` service's `temporal` database |
| `temporal-ui` | `temporalio/ui:latest` | `8080:8080` | Temporal Web UI, `TEMPORAL_ADDRESS=temporal:7233` |

Ports were chosen against `lsof -iTCP -sTCP:LISTEN -P` on the reference dev machine: `5183` (Kaneo), `9000`/`9001` (an unrelated local MinIO container) and `3000` (an unrelated local dev server) were taken, so MinIO here uses `9010`/`9011`; Postgres/Valkey/Mailpit/Temporal keep their defaults (`5432`, `6379`, `1025`, `8025`, `7233`, `8080`), all free at spec time. Port `8000` is free and is reserved for the backend API dev server (CQ-004's `make api`) — not a compose service, so it isn't listed here. Re-run the same `lsof` check before implementing; if a port is now taken, change the mapping here **and** in CQ-002's `.env.example` together — they must never disagree.

Decision: Temporal reuses the `postgres` service (a second database named `temporal`, created by an init SQL script mounted at `/docker-entrypoint-initdb.d/`) instead of a dedicated Postgres container, to keep the local compose file small. This is a local-only shortcut; production (CQ-035) uses Railway's Temporal template with its own Postgres per `docs/roadmap.md` Decisions log #G5.

## Health checks (pin exactly)

- `postgres`: `pg_isready -U cq`
- `valkey`: `valkey-cli ping` (falls back to `redis-cli ping` if the image lacks `valkey-cli`)
- `minio`: `curl -f http://localhost:9000/minio/health/live` (container-internal port, not the remapped host port)
- `mailpit`: no compose healthcheck needed; reachability is proven by AC3 below
- `temporal` / `temporal-ui`: `depends_on: postgres: condition: service_healthy`; reachability proven by AC3

`make up` = `docker compose -f infra/docker-compose.yml up -d --wait` (fails if any service doesn't reach `healthy` within compose's default timeout). `make down` = `docker compose -f infra/docker-compose.yml down`. `make logs` = `docker compose -f infra/docker-compose.yml logs -f`.

## Acceptance criteria

- [ ] AC1 — All services healthy; Temporal UI and Mailpit reachable in the browser (roadmap exit check).
- [ ] AC2 — `docker compose -f infra/docker-compose.yml ps` shows every service in the table above as `Up`/`healthy`.
- [ ] AC3 — `curl -sf http://localhost:8025` (Mailpit UI) and `curl -sf http://localhost:8080` (Temporal UI) both return HTTP 200.
- [ ] AC4 — Postgres has `cq_dev`, `cq_test`, and `temporal` databases: `docker compose exec postgres psql -U cq -d cq_dev -c '\l'` lists all three.
- [ ] AC5 — The `clear-quote` and `clearquote-demo-docs` buckets exist in MinIO after `make up` with no manual step: `MINIO_DEFAULT_BUCKETS` creates both at container start (see post-dev.md follow-up fix; superseded the earlier `minio-init` one-shot container).
- [ ] AC6 — `make down` stops and removes all containers cleanly; a second `make up` afterwards succeeds from a clean state.

## Test plan

| Criterion | Test type | Test name / command |
| --- | --- | --- |
| AC1, AC2 | Manual/shell | `make up && docker compose -f infra/docker-compose.yml ps` |
| AC3 | Shell | `curl -sf -o /dev/null -w '%{http_code}' http://localhost:8025`; same for `:8080` |
| AC4 | Shell | `docker compose -f infra/docker-compose.yml exec postgres psql -U cq -d cq_dev -c '\l'` |
| AC5 | Shell | `docker run --rm --network clear-quote_default --entrypoint sh bitnamilegacy/minio-client:latest -c "mc alias set local http://minio:9000 cq-minio cq-minio-secret && mc ls local/"` (or check `minio` container logs for bucket creation at boot) |
| AC6 | Shell | `make down && make up` |

## Notes for the agent

- Decision: `valkey/valkey:7-alpine` speaks the Redis protocol; the app connects via `VALKEY_URL=redis://...` using a standard Redis client (`redis.asyncio`, pinned in CQ-004's spec) — there is no Valkey-specific client library needed.
- Decision: verify `temporalio/auto-setup`'s exact env vars (`DB`, `DB_PORT`, `POSTGRES_SEEDS`, `POSTGRES_USER`, `POSTGRES_PWD`) against the image's current README before wiring. If that image can't cleanly point at an existing external Postgres, fall back to a dedicated `temporal-postgres` service (still not exposed to the host) and log the change as a `Decision:` in `plan.md`.
- Keep `.env.example` (CQ-002) and this compose file's defaults in sync — same variable names, same port numbers, always.
- Follow the agent loop in `AGENTS.md`. Log small decisions in `plan.md`; raise big gaps in Kaneo.
