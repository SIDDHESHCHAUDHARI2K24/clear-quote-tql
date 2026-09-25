import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  applicationIdByClientEmail,
  closeDbPool,
  execSql,
  flushLoginRateLimit,
  queryRows,
} from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

const REPO_ROOT = path.resolve(__dirname, "../..");

// P5 milestone (docs/backlog/phase-p5-p6-plan.md "Verification (phase
// level)"): "as a Manager, the dashboard counts match the seed (CQ-025
// AC1). Resolving Aisha's missing-occupancy flag in the workspace takes
// her to Priced, and she leaves the attention list." This is the
// cross-item proof that the two land together, not a re-test of either
// item's own ACs: CQ-025's post-dev.md covers the tiles' href/count
// consistency (dashboard-tiles.spec.ts), and CQ-028's post-dev.md covers
// Aisha's resume through the real UI+pipeline
// (aisha-occupancy-resume.spec.ts, whose header comment this one mirrors
// for the restore). Both counts here are computed independently via SQL
// (`queryRows`), not by re-reading the same `GET /dashboard` response
// under test, and reuses `staffLogin`/`applicationIdByClientEmail`/
// `execSql` rather than reinventing them.
//
// Needs `.env`'s SEED_STAFF_PASSWORD, `make demo-reset`'s seeded
// personas, and a running API + `make worker` on this worktree's slot
// (the occupancy edit resumes a real Temporal pipeline run).
const password = process.env.SEED_STAFF_PASSWORD;
const MANAGER = "casey.nguyen@clearquote-demo.test";
const AISHAS_LO = "jordan.lee@clearquote-demo.test";
const EVIDENCE_DIR = "docs/backlog/evidence/p56-phase";
// This project (`cross-app`, playwright.config.ts) has no `baseURL` of its
// own -- both borrower-action-reflects-in-console.spec.ts and this spec
// drive an app via an explicit `browser.newContext({ baseURL })`, not the
// default `page` fixture.
const LO_BASE_URL = process.env.LO_BASE_URL ?? "http://localhost:3010";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

// Same restore as aisha-occupancy-resume.spec.ts (own comment there has
// the full rationale): `write_flag`/`resolve_flag` only ever set
// `resolved_at`, never delete, so re-opening the exact
// (occupancy_type, ob_required_field) row reproduces the original seeded
// flag, and `updated_at = 'epoch'` undoes the ORM `onupdate` so she still
// sorts first in the "Needs your attention" list's `updated_at.asc()`
// order for any later run.
//
// Extra, beyond that spec's own restore: this file also deletes any
// `scenarios`/`quotes` rows and any *other* flag her pipeline run raised
// (e.g. an assets-vs-reserves check), leaving DB state indistinguishable
// from a fresh `make demo-reset`. `activity_events` rows are left in
// place -- the pipeline run's own history, harmless once `scenarios`/
// `quotes` are gone.
function cleanupAishasPipelineArtifacts(applicationId: string): void {
  execSql(
    `delete from quotes where scenario_id in ` +
      `(select id from scenarios where application_id = '${applicationId}');`,
  );
  execSql(`delete from scenarios where application_id = '${applicationId}';`);
  execSql(
    `delete from flags where application_id = '${applicationId}' ` +
      `and not (field_key = 'occupancy_type' and rule = 'ob_required_field');`,
  );
  execSql(
    `update applications set status = 'needs_attention', occupancy = null, ` +
      `last_pipeline_stage = null, recommended_quote_id = null, updated_at = 'epoch' ` +
      `where id = '${applicationId}';`,
  );
  execSql(
    `update flags set resolved_at = null where application_id = '${applicationId}' ` +
      `and field_key = 'occupancy_type' and rule = 'ob_required_field' ` +
      `and resolved_at is not null;`,
  );
}

// A real, app-observed constraint found while building this spec:
// `reverify.py::_plan_resume` deliberately never repeats a *completed*
// Temporal run ("A completed (priced) run is never repeated" -- review
// minor 6) -- an application prices once per `make demo-reset`. SQL can
// restore the `applications`/`flags` rows to look freshly seeded again,
// but it cannot revive the spent Temporal workflow behind them,
// so a second real resume attempt in the same suite pass silently does
// nothing (a different, "already finished" outcome -- no toast, no
// re-price). Both this spec and `aisha-occupancy-resume.spec.ts`
// (CQ-028 AC1, `lo-console`, which Playwright runs before `cross-app`)
// perform this exact real resume against one shared demo-reset, so by
// the time this test reaches her, her one real run is already spent.
// `backend/scripts/restart_pipeline.py` (test-only) starts a genuinely
// fresh Temporal run for her, exactly as `make demo-reset` would have --
// it changes no pricing/verification logic, only which run id is live.
function restartAishasPipeline(): void {
  execFileSync(
    "uv",
    ["run", "python", "backend/scripts/restart_pipeline.py", "--persona", "aisha_coleman"],
    { cwd: REPO_ROOT, encoding: "utf-8" },
  );
}

test.afterAll(async () => {
  const applicationId = applicationIdByClientEmail("aisha.coleman@clearquote-demo.test");
  cleanupAishasPipelineArtifacts(applicationId);
  await closeDbPool();
});

async function scalar(sql: string): Promise<number> {
  const rows = await queryRows<{ count: string }>(sql);
  return Number(rows[0]?.count ?? 0);
}

test("P5 milestone: Manager dashboard tiles match the seed, then resolving Aisha's flag takes her to Priced", async ({
  browser,
}) => {
  // Two full OTP logins (Manager, then Aisha's LO) plus the dashboard-tile
  // SQL cross-check plus aisha-occupancy-resume.spec.ts's own
  // occupancy-edit -> resume -> Priced chain (a real multi-step Temporal
  // pipeline: verify -> enrich x3 -> auto-price) -- more room than that
  // spec's own 120s (which only has the one login + the pipeline wait).
  test.setTimeout(150_000);

  // Two separate contexts, not one page re-logged-in: `middleware.ts`
  // redirects `/login` straight to `/` whenever its session cookie is
  // already set, so reusing one context for both logins would leave the
  // second `staffLogin` stuck forever waiting for a login form that a
  // still-signed-in Manager session never renders (first full run hung
  // here for the entire test budget). Same reasoning as
  // borrower-action-reflects-in-console.spec.ts's two contexts, just both
  // against the LO console instead of one each app.
  const managerContext = await browser.newContext({ baseURL: LO_BASE_URL });
  const page = await managerContext.newPage();

  await staffLogin(page, MANAGER, password!);
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();

  // -- Tile counts, computed independently via SQL (dashboard/service.py's
  // own tile queries, mirrored here) -------------------------------------
  const [clients, applications, preApprovalsSent, withProperty, awaitingReview, needsAttention, staleQuotes] =
    await Promise.all([
      scalar(`select count(distinct client_id) from applications`),
      scalar(`select count(*) from applications where status not in ('withdrawn', 'closed')`),
      scalar(`
        select count(*) from applications a
        where a.status in ('sent', 'viewed', 'inquiry', 'option_selected')
           or (
             a.status = 'stale' and exists (
               select 1 from quote_package_versions v
               join quote_packages p on p.id = v.package_id
               where p.application_id = a.id
             )
           )
      `),
      scalar(
        `select count(distinct a.id) from applications a ` +
          `join properties p on p.application_id = a.id ` +
          `where p.address_status = 'specific_address'`,
      ),
      scalar(`select count(*) from applications where status in ('priced', 'inquiry', 'option_selected')`),
      scalar(`select count(*) from applications where status = 'needs_attention'`),
      scalar(`select count(*) from applications where status = 'stale'`),
    ]);

  const expectedByTileLabel: Record<string, number> = {
    Clients: clients,
    Applications: applications,
    "Pre-approvals sent": preApprovalsSent,
    "With a property": withProperty,
    "Awaiting your review": awaitingReview,
    "Needs attention": needsAttention,
    "Stale quotes": staleQuotes,
  };

  const tiles = page.getByRole("region", { name: "Dashboard tiles" });
  for (const [label, expectedCount] of Object.entries(expectedByTileLabel)) {
    const link = tiles.getByRole("link", { name: new RegExp(`${label}$`) });
    const text = (await link.textContent()) ?? "";
    const displayedCount = Number(text.trim().match(/^\d+/)?.[0]);
    expect(displayedCount, `"${label}" tile vs. the seed`).toBe(expectedCount);
  }
  await page.screenshot({ path: `${EVIDENCE_DIR}/p5-milestone-dashboard.png`, fullPage: true });
  await managerContext.close();

  // -- As an LO, resolve Aisha's missing-occupancy flag in the workspace -
  const applicationId = applicationIdByClientEmail("aisha.coleman@clearquote-demo.test");
  // Reset her DB rows AND give her a fresh Temporal run (see
  // restartAishasPipeline's own comment: aisha-occupancy-resume.spec.ts,
  // in `lo-console`, already spent her one real run this demo-reset by
  // the time `cross-app` gets here).
  cleanupAishasPipelineArtifacts(applicationId);
  restartAishasPipeline();

  // The fresh run's import -> verify chain must reach needs_attention
  // (and wait there for the resume signal) before the edit below can
  // signal it; poll rather than guess a fixed delay.
  const pollDeadline = Date.now() + 30_000;
  let reachedNeedsAttention = false;
  while (Date.now() < pollDeadline) {
    const rows = await queryRows<{ status: string }>(
      `select status from applications where id = $1`,
      [applicationId],
    );
    if (rows[0]?.status === "needs_attention") {
      reachedNeedsAttention = true;
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  expect(reachedNeedsAttention, "Aisha's restarted pipeline should reach needs_attention").toBe(
    true,
  );

  flushLoginRateLimit();
  const loContext = await browser.newContext({ baseURL: LO_BASE_URL });
  const loPage = await loContext.newPage();
  await staffLogin(loPage, AISHAS_LO, password!);

  await loPage.goto(`/applications/${applicationId}/property`);
  await expect(loPage.getByRole("heading", { name: "Property" })).toBeVisible();
  await expect(loPage.getByText("Occupancy", { exact: true })).toBeVisible();

  const loanCard = loPage.locator("section", { has: loPage.getByRole("heading", { name: "Loan" }) });
  await loanCard.getByRole("button", { name: "Edit" }).first().click();
  await loPage.getByLabel("Occupancy").selectOption("investment");
  await loPage.getByRole("button", { name: "Save" }).click();

  await expect(
    loPage.getByRole("status").filter({ hasText: "All checks pass — pricing resumed" }),
  ).toBeVisible({ timeout: 10_000 });
  await expect(loPage.getByText("Priced", { exact: true })).toBeVisible({ timeout: 60_000 });
  await loPage.screenshot({ path: `${EVIDENCE_DIR}/p5-milestone-aisha-priced.png` });

  // -- She leaves "Needs your attention" within one refresh --------------
  await loPage.goto("/");
  await expect(loPage.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  const attention = loPage.locator("section", {
    has: loPage.getByRole("heading", { name: "Needs your attention" }),
  });
  await expect(attention.getByText("Aisha Coleman")).toHaveCount(0);
  await loPage.screenshot({ path: `${EVIDENCE_DIR}/p5-milestone-dashboard-after.png`, fullPage: true });

  await loContext.close();
});
