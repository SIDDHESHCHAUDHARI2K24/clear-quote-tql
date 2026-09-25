import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

// Test-only DB lookups: the LO console has no applications list yet
// (CQ-025-027), so a workspace spec needs another way to find a seeded
// persona's application id -- `docker compose exec postgres psql` against
// this worktree's own dev DB (read from the repo-root `.env`'s
// `DATABASE_URL`, written by `scripts/worktree-env.sh <slot>`), not a new
// backend endpoint. IDs are `uuid4()`'d fresh by every `make demo-reset`,
// so this must run at test time, never hardcoded.
const REPO_ROOT = path.resolve(__dirname, "../..");

function databaseName(): string {
  const envPath = path.join(REPO_ROOT, ".env");
  const content = readFileSync(envPath, "utf-8");
  const match = content.match(/^DATABASE_URL=.*\/([\w-]+)\s*$/m);
  if (!match) {
    throw new Error(`Could not find DATABASE_URL in ${envPath}`);
  }
  return match[1];
}

function psql(sql: string): string {
  return execFileSync(
    "docker",
    [
      "compose",
      "-f",
      "infra/docker-compose.yml",
      "exec",
      "-T",
      "postgres",
      "psql",
      "-U",
      "cq",
      "-d",
      databaseName(),
      "-tAc",
      sql,
    ],
    { cwd: REPO_ROOT, encoding: "utf-8" },
  ).trim();
}

// Returns the application id for the (single) application belonging to the
// client with this email -- every seeded persona (seed/personas/*.yaml) has
// exactly one.
export function applicationIdByClientEmail(email: string): string {
  const id = psql(
    `select a.id from applications a join clients c on c.id = a.client_id where c.email = '${email}' limit 1;`,
  );
  if (!id) {
    throw new Error(`No application found for client email ${email} -- run make demo-reset first`);
  }
  return id;
}

function valkeyDbIndex(): string {
  const envPath = path.join(REPO_ROOT, ".env");
  const content = readFileSync(envPath, "utf-8");
  const match = content.match(/^VALKEY_URL=.*\/(\d+)\s*$/m);
  if (!match) {
    throw new Error(`Could not find VALKEY_URL in ${envPath}`);
  }
  return match[1];
}

// A workspace spec that does several real staff logins (each one a real
// email+password+OTP round trip) can trip the staff login endpoint's own
// abuse-prevention rate limit (`auth/staff/service.py`, Valkey-backed)
// within a single run -- flushing this worktree's own Valkey db between
// logins keeps the suite deterministic without weakening the real limit
// (this never touches another worktree's db, see `valkeyDbIndex`).
export function flushLoginRateLimit(): void {
  execFileSync(
    "docker",
    [
      "compose",
      "-f",
      "infra/docker-compose.yml",
      "exec",
      "-T",
      "valkey",
      "valkey-cli",
      "-n",
      valkeyDbIndex(),
      "flushdb",
    ],
    { cwd: REPO_ROOT },
  );
}
