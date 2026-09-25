#!/usr/bin/env bash
# Per-worktree environment for parallel P3/P4 and P5/P6 workers (P3/P4
# foundation, docs/backlog/phase-p3-p4-foundation.md; extended by the P5/P6
# foundation, docs/backlog/phase-p5-p6-foundation.md). Each worker/slot N gets its own
# Postgres databases, Valkey db, Temporal task queue and port range so N
# worktrees can run `make demo-reset` + the API + both Next.js apps at the
# same time against the one shared `make up` stack, without colliding.
#
# Usage: scripts/worktree-env.sh <slot>
#   P3/P4 (docs/backlog/phase-p3-p4-plan.md "E2E recipe"):
#   slot 1 = foundation, 2 = CQ-021, 3 = CQ-016, 4 = CQ-022, 5 = CQ-017,
#   6 = CQ-023, 7 = CQ-024, 8 = CQ-018, 9 = CQ-019, 10 = CQ-020
#   P5/P6 (docs/backlog/phase-p5-p6-plan.md "Work units and waves"):
#   slot 11 = P5/P6 foundation, 12 = CQ-025, 13 = CQ-027, 14 = CQ-028a,
#   15 = CQ-029, 16 = CQ-030, 17 = CQ-031, 18 = CQ-032a, 19 = CQ-034,
#   20 = CQ-026, 21 = CQ-028b, 22 = CQ-032b, 23 = CQ-033
#
# Slot N -> DBs cq_dev_s<N>/cq_test_s<N>, Valkey db N+2, API 8100+N,
# LO console 3100+N, portal 3200+N, Temporal queue cq-s<N>. Valkey must run
# with enough logical databases for db N+2 (infra/docker-compose.yml starts
# it with `--databases 64`; an older container still on the default 16
# fails the check below for slots >= 14 -- recreate it with
# `docker compose -f infra/docker-compose.yml up -d valkey`).
#
# Writes (idempotent -- rerunning patches the same `KEY=value` lines in
# place via `set_kv_in`, appends a line only if that key is missing, and
# never touches any other line already in the file, so anything a
# developer added by hand to one of these -- including a line unrelated to
# this script -- survives a rerun):
#   - <repo-root>/.env                       (backend + seed)
#   - apps/lo-console/.env.local             (NEXT_PUBLIC_API_URL)
#   - apps/borrower-portal/.env.local        (NEXT_PUBLIC_API_URL)
# Creates cq_dev_s<N> / cq_test_s<N> in the shared Postgres container if
# missing. Never touches cq_dev, cq_test, cq_dev_p2 or cq_test_p2.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

SLOT="${1:-}"
if [[ -z "$SLOT" || ! "$SLOT" =~ ^[0-9]+$ ]]; then
  echo "usage: scripts/worktree-env.sh <slot>" >&2
  echo "  slot must be a positive integer (see docs/backlog/phase-p3-p4-plan.md)" >&2
  exit 1
fi

DEV_DB="cq_dev_s${SLOT}"
TEST_DB="cq_test_s${SLOT}"
VALKEY_DB=$((SLOT + 2))
API_PORT=$((8100 + SLOT))
LO_PORT=$((3100 + SLOT))
PORTAL_PORT=$((3200 + SLOT))
TASK_QUEUE="cq-s${SLOT}"

# Guard rail: never let a typo'd slot resolve to a shared/protected DB name.
for protected in cq_dev cq_test cq_dev_p2 cq_test_p2; do
  if [[ "$DEV_DB" == "$protected" || "$TEST_DB" == "$protected" ]]; then
    echo "refusing to target protected database '$protected'" >&2
    exit 1
  fi
done

# Guard rail: the slot's Valkey db must exist on the shared Valkey. Skipped
# (with a note) when the container isn't reachable, e.g. before `make up`.
VALKEY_DATABASES="$(docker exec clear-quote-valkey-1 valkey-cli CONFIG GET databases 2>/dev/null | tail -n1 || true)"
if [[ "$VALKEY_DATABASES" =~ ^[0-9]+$ ]]; then
  if (( VALKEY_DB >= VALKEY_DATABASES )); then
    echo "slot ${SLOT} needs Valkey db ${VALKEY_DB}, but the running Valkey has only ${VALKEY_DATABASES} databases (0-$((VALKEY_DATABASES - 1)))." >&2
    echo "recreate it with the compose setting (--databases 64): docker compose -f infra/docker-compose.yml up -d valkey" >&2
    exit 1
  fi
else
  echo "note: could not read the Valkey databases count (is \`make up\` running?); skipping the db range check" >&2
fi

ENV_FILE="$REPO_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp "$REPO_ROOT/.env.example" "$ENV_FILE"
  echo "created $ENV_FILE from .env.example"
fi

# set_kv_in FILE KEY VALUE: replaces an existing `KEY=...` line (commented
# or not) in FILE with `KEY=VALUE`, or appends one if the key isn't present
# at all -- every other line in FILE is left untouched. Uses a temp file +
# mv so this is safe to rerun. Creates FILE (empty) first if it doesn't
# exist yet, so this same helper works for a brand-new apps/*/.env.local
# and for the pre-existing root .env alike -- a rerun patches in place
# rather than truncating/overwriting the whole file, so any line a
# developer added by hand (to either file) survives.
set_kv_in() {
  local file="$1" key="$2" value="$3"
  local tmp
  [[ -f "$file" ]] || : > "$file"
  tmp="$(mktemp)"
  if grep -qE "^#?${key}=" "$file"; then
    awk -v k="$key" -v v="$value" '
      BEGIN { FS=OFS="=" }
      $0 ~ "^#?" k "=" { print k "=" v; next }
      { print }
    ' "$file" > "$tmp"
    mv "$tmp" "$file"
  else
    rm -f "$tmp"
    echo "${key}=${value}" >> "$file"
  fi
}

# set_kv KEY VALUE: set_kv_in against $ENV_FILE (the root .env).
set_kv() {
  set_kv_in "$ENV_FILE" "$1" "$2"
}

# get_kv KEY: current value (empty string if unset or blank).
get_kv() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true
}

random_hex() {
  uv run python -c "import secrets; print(secrets.token_hex(32))"
}

random_fernet_key() {
  uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

set_kv "DATABASE_URL" "postgresql+asyncpg://cq:cq@localhost:5432/${DEV_DB}"
set_kv "TEST_DATABASE_URL" "postgresql+asyncpg://cq:cq@localhost:5432/${TEST_DB}"
set_kv "VALKEY_URL" "redis://localhost:6379/${VALKEY_DB}"
set_kv "TEMPORAL_TASK_QUEUE" "$TASK_QUEUE"
# pytest's `valkey` fixture FLUSHDBs TEST_VALKEY_URL's db (default db 15,
# shared by every worktree -- and equal to slot 13's dev db). With a 64-db
# Valkey, give each slot its own test db 32+N instead.
TEST_VALKEY_DB=$((SLOT + 32))
if [[ "$VALKEY_DATABASES" =~ ^[0-9]+$ ]] && (( TEST_VALKEY_DB < VALKEY_DATABASES )); then
  set_kv "TEST_VALKEY_URL" "redis://localhost:6379/${TEST_VALKEY_DB}"
elif (( VALKEY_DB == 15 )); then
  echo "warning: slot ${SLOT}'s Valkey db 15 is also pytest's default test db; recreate Valkey with 64 databases (see above) before running pytest and the dev stack together" >&2
fi
set_kv "CORS_ORIGINS" "http://localhost:${LO_PORT},http://localhost:${PORTAL_PORT}"
# CQ-020: the emailed report link points at this slot's borrower portal.
set_kv "PORTAL_BASE_URL" "http://localhost:${PORTAL_PORT}"

if [[ -z "$(get_kv SECRET_KEY)" || "$(get_kv SECRET_KEY)" == "change-me" ]]; then
  set_kv "SECRET_KEY" "$(random_hex)"
fi

if [[ -z "$(get_kv FIELD_ENCRYPTION_KEY)" ]]; then
  set_kv "FIELD_ENCRYPTION_KEY" "$(random_fernet_key)"
fi

if [[ -z "$(get_kv SEED_STAFF_PASSWORD)" ]]; then
  set_kv "SEED_STAFF_PASSWORD" "$(random_hex | cut -c1-20)"
fi

if [[ -z "$(get_kv SEED_BORROWER_PASSWORD)" ]]; then
  set_kv "SEED_BORROWER_PASSWORD" "$(random_hex | cut -c1-20)"
fi

# Any other blank SEED_* var in .env.example (SEED_RNG_SEED,
# SEED_FAST_ADAPTERS today) is left as-is -- those aren't secrets, they're
# tuning knobs with their own code-level defaults (seed/config.py), so a
# blank/absent line there isn't a "needs a random value" case.

echo "creating databases if missing..."
for db in "$DEV_DB" "$TEST_DB"; do
  exists="$(docker exec clear-quote-postgres-1 psql -U cq -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${db}'")"
  if [[ "$exists" != "1" ]]; then
    docker exec clear-quote-postgres-1 psql -U cq -d postgres -c "CREATE DATABASE ${db}"
    echo "  created ${db}"
  else
    echo "  ${db} already exists"
  fi
done

for app_dir in "apps/lo-console" "apps/borrower-portal"; do
  local_env="$REPO_ROOT/$app_dir/.env.local"
  set_kv_in "$local_env" "NEXT_PUBLIC_API_URL" "http://localhost:${API_PORT}"
  echo "wrote $local_env"
done

# Slot ports/queue this worker needs for the rest of the session (uvicorn,
# `pnpm ... next dev -p`, `make e2e`). Not written to any file -- print
# them and export the Playwright base URLs for the current shell only
# (`source scripts/worktree-env.sh <slot>` to keep the exports; a plain
# invocation still prints everything a worker needs to copy/paste).
export LO_BASE_URL="http://localhost:${LO_PORT}"
export PORTAL_BASE_URL="http://localhost:${PORTAL_PORT}"

cat <<EOF

slot ${SLOT}:
  DATABASE_URL      -> ${DEV_DB}
  TEST_DATABASE_URL -> ${TEST_DB}
  VALKEY_URL        -> db ${VALKEY_DB}
  TEMPORAL_TASK_QUEUE -> ${TASK_QUEUE}
  API_PORT          = ${API_PORT}   (uv run uvicorn app.main:app --port ${API_PORT})
  LO_PORT           = ${LO_PORT}    (pnpm --filter @cq/lo-console exec next dev -p ${LO_PORT})
  PORTAL_PORT       = ${PORTAL_PORT} (pnpm --filter @cq/borrower-portal exec next dev -p ${PORTAL_PORT})
  LO_BASE_URL       = ${LO_BASE_URL}
  PORTAL_BASE_URL   = ${PORTAL_BASE_URL}

Run \`make e2e\` with LO_BASE_URL/PORTAL_BASE_URL set as above (export them,
or \`source scripts/worktree-env.sh ${SLOT}\` in the shell that runs Playwright).
EOF
