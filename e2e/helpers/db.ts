import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

import { Pool } from "pg";

// Test-only DB lookups shared by both apps' specs.
//
// CQ-016: the LO console has no applications list yet (CQ-025-027), so a
// workspace spec needs another way to find a seeded persona's application
// id -- `docker compose exec postgres psql` against this worktree's own
// dev DB (read from the repo-root `.env`'s `DATABASE_URL`, written by
// `scripts/worktree-env.sh <slot>`), not a new backend endpoint. IDs are
// `uuid4()`'d fresh by every `make demo-reset`, so this must run at test
// time, never hardcoded.
//
// CQ-022's E2E recipe (docs/backlog/CQ-022-borrower-report/spec.md, the
// worker prompt): "GET their report by token (look the token up in the
// DB)". There's no UI path to a borrower's report token yet (the real
// home/status page with a report link is CQ-031, out of this item's
// scope), so those specs use a direct `pg` (node-postgres) connection
// instead of shelling out to `psql` -- `DATABASE_URL` is a SQLAlchemy-style
// `postgresql+asyncpg://` URL; `pg` wants the plain `postgresql://` scheme.
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

// Runs a write statement (UPDATE/DELETE/INSERT) directly against this
// worktree's Postgres via `docker compose exec psql` -- for spec cleanup
// only (e.g. a full-suite `afterAll` that undoes a shared persona's own
// mutation so a later spec file sees her original seeded state; see
// `aisha-occupancy-resume.spec.ts` and `apply-wizard-resume.spec.ts`).
// Discards any returned rows -- use a real `pg` query via `getPool()`
// instead if you need the result.
export function execSql(sql: string): void {
  psql(sql);
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

// CQ-034 spec.md AC4: the borrower_accounts.id the support rate limit key
// (`rl:support:borrower:{id}`) is keyed on -- distinct from `clients.id`
// (applicationIdByClientEmail's join target).
export function borrowerAccountIdByEmail(email: string): string {
  const id = psql(
    `select id from borrower_accounts where lower(email) = lower('${email}') limit 1;`,
  );
  if (!id) {
    throw new Error(
      `No borrower_accounts row found for ${email} -- run make demo-reset (with SEED_BORROWER_PASSWORD set) first`,
    );
  }
  return id;
}

// CQ-034 spec.md AC4 ("the rate-limit test may flush only this borrower's
// rl:* key"): deletes exactly one Valkey key, `rl:support:borrower:
// {borrowerAccountId}` (service.py's `_RATE_LIMIT_KEY_PREFIX`) -- not a
// `rl:*` wildcard sweep like `flushLoginRateLimit`, so a run of this test
// never clears another persona's or another rate-limited action's
// counters mid-suite.
export function flushSupportRateLimit(borrowerAccountId: string): void {
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
      "del",
      `rl:support:borrower:${borrowerAccountId}`,
    ],
    { cwd: REPO_ROOT },
  );
}

// A workspace spec that does several real staff logins (each one a real
// email+password+OTP round trip) can trip the staff login endpoint's own
// abuse-prevention rate limit (`auth/staff/service.py`, Valkey-backed)
// within a single run -- clearing this worktree's rate-limit keys between
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
      // Only the login rate-limit counters (`rl:*`, auth/otp/rate_limit.py)
      // -- not the whole db, which would also drop the borrower sessions
      // `e2e/global-setup.ts` saved for the report specs (P5/P6
      // foundation: a full-suite run broke on exactly that).
      "eval",
      "for _, k in ipairs(redis.call('keys', ARGV[1])) do redis.call('del', k) end",
      "0",
      "rl:*",
    ],
    { cwd: REPO_ROOT },
  );
}

let pool: Pool | undefined;

function nodePgConnectionString(databaseUrl: string): string {
  return databaseUrl.replace(/^postgresql\+asyncpg:\/\//, "postgresql://");
}

function getPool(): Pool {
  if (!pool) {
    const databaseUrl = process.env.DATABASE_URL;
    if (!databaseUrl) {
      throw new Error(
        "DATABASE_URL is not set -- run `scripts/worktree-env.sh <slot>` first (see e2e recipe).",
      );
    }
    pool = new Pool({ connectionString: nodePgConnectionString(databaseUrl) });
  }
  return pool;
}

/**
 * Runs a read query directly against this worktree's Postgres and returns
 * its rows -- for spec-time assertions that need to compute an expected
 * value independently of the endpoint under test (e.g. a milestone spec
 * recomputing dashboard tile counts from the seed via SQL rather than
 * re-reading `GET /dashboard`'s own answer). Unlike `execSql` (fire-and-
 * forget, `psql -tAc`, for writes), this goes through the same `pg` pool
 * as `latestReportTokenForBorrower` so typed rows come back.
 */
export async function queryRows<T extends Record<string, unknown> = Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  const { rows } = await getPool().query<T>(sql, params);
  return rows;
}

/**
 * The most recently sent, non-superseded `quote_package_versions.
 * report_token` for the client whose email matches `borrowerEmail`
 * (case-insensitive) -- e.g. a seeded persona like
 * `luis.romero@clearquote-demo.test`. Throws if none exists (the persona
 * needs a `fixture_layer` in its seed YAML, per `seed/loader.py::apply_
 * send_fixture`).
 */
export async function latestReportTokenForBorrower(borrowerEmail: string): Promise<string> {
  const { rows } = await getPool().query<{ report_token: string }>(
    `select v.report_token
       from quote_package_versions v
       join quote_packages p on p.id = v.package_id
       join applications a on a.id = p.application_id
       join clients c on c.id = a.client_id
      where lower(c.email) = lower($1)
      order by v.sent_at desc
      limit 1`,
    [borrowerEmail],
  );
  if (rows.length === 0) {
    throw new Error(`No quote_package_versions row found for borrower ${borrowerEmail}`);
  }
  return rows[0].report_token;
}

/** Call once at the end of a spec file's tests (e.g. in `test.afterAll`) to
 * release the pool's connections instead of leaving the Playwright worker
 * process hanging open. */
export async function closeDbPool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = undefined;
  }
}
