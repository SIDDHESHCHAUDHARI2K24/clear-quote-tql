import { Pool } from "pg";

// CQ-022's E2E recipe (docs/backlog/CQ-022-borrower-report/spec.md, the
// worker prompt): "GET their report by token (look the token up in the
// DB)". There's no UI path to a borrower's report token yet (the real
// home/status page with a report link is CQ-031, out of this item's
// scope), so specs that need one look it up directly against the same
// Postgres the worktree's API/portal talk to -- `DATABASE_URL` (set by
// `scripts/worktree-env.sh`) is a SQLAlchemy-style `postgresql+asyncpg://`
// URL; `pg` (node-postgres) wants the plain `postgresql://` scheme.

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
