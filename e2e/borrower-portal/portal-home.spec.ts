import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { Pool } from "pg";

import {
  applicationIdByClientEmail,
  borrowerAccountIdByEmail,
  closeDbPool,
  execSql,
  flushLoginRateLimit,
} from "../helpers/db";
import { borrowerLogin } from "../helpers/borrowerLogin";

// CQ-031 spec.md AC1-AC4/AC6: the real seeded personas, driven through the
// UI, against a running stack (slot 17 -- see docs/backlog/
// phase-p5-p6-worker-guide.md's E2E recipe). AC5 (isolation) is an API-only
// test (backend/app/features/portal/home/tests/test_router.py) -- nothing
// in the UI exposes another borrower's data to assert against here.
const REPO_ROOT = path.resolve(__dirname, "../..");
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

test.afterAll(async () => {
  await closeDbPool();
});

// Loading `/apply` (AC4's own test, below) opens and autosaves a real,
// open `application_drafts` row for this same seeded "no application"
// borrower -- `apply-wizard-resume.spec.ts` (CQ-032) already has to clean
// up its own, larger draft for the same reason (its own comment there);
// this one is CQ-031's own leak, into `shell.spec.ts`'s later "No
// application yet" assertion for the same persona. Delete it, not just
// the one from that other spec, so this file leaves her exactly as seeded
// no matter which of the two runs last in a full-suite pass. In
// `afterAll`, not inline at the end of the AC4 test body (review finding):
// the draft is created as soon as `/apply` loads, before that test's own
// "Apply" heading assertion -- if that assertion is ever slow/flaky and
// times out, an inline delete after it would never run.
test.afterAll(() => {
  const borrowerAccountId = borrowerAccountIdByEmail("noapp.borrower@clearquote-demo.test");
  execSql(
    `delete from application_drafts where borrower_account_id = '${borrowerAccountId}' ` +
      `and submitted_application_id is null;`,
  );
});

async function expectNoHorizontalScroll(page: Page) {
  const [scrollWidth, clientWidth] = await Promise.all([
    page.evaluate(() => document.documentElement.scrollWidth),
    page.evaluate(() => document.documentElement.clientWidth),
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
}

// Marcus Hale is seeded `priced`, not `sent` (seed/personas/p01_marcus_
// hale.yaml) -- AC3 needs a real sent version to exercise "See your
// numbers", so freeze one the same way CQ-024's own AC1 does (this file's
// docstring / worker guide's E2E note): the dev script that reuses the
// same `freeze_package_version` factory CQ-020's real send workflow will
// call. Idempotent (reuses an existing unexpired, non-superseded version).
function freezeMarcusHaleVersion(): void {
  execFileSync(
    "uv",
    ["run", "python", "backend/scripts/freeze_sent_version.py", "--persona", "marcus_hale"],
    { cwd: REPO_ROOT, stdio: "inherit" },
  );
}

test("AC1/AC2: Aisha Coleman (needs_attention) sees 'Application received', no internal wording", async ({
  page,
}) => {
  await borrowerLogin(page, "aisha.coleman@clearquote-demo.test", password!);

  await expect(page.getByText("Application received")).toBeVisible();

  const bodyText = (await page.locator("body").innerText()).toLowerCase();
  for (const word of ["attention", "flag", "error"]) {
    expect(bodyText).not.toContain(word);
  }
});

test("AC3: Marcus Hale's 'See your numbers' opens his latest sent version", async ({ page }) => {
  freezeMarcusHaleVersion();

  await borrowerLogin(page, "marcus.hale@clearquote-demo.test", password!);
  // `freeze_sent_version.py` sets the application to `sent` (spec.md's
  // mapping: `sent` -> preapproved, "Your pre-approval is ready").
  await expect(page.getByText("Your pre-approval is ready")).toBeVisible();

  const button = page.getByRole("button", { name: "See your numbers" });
  await expect(button).toBeVisible();
  await button.click();
  await page.waitForURL(/\/report\//);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();
});

test("AC3: Luis Romero (option_selected) has no primary action, reaches his report via 'View your numbers'", async ({
  page,
}) => {
  await borrowerLogin(page, "luis.romero@clearquote-demo.test", password!);

  await expect(page.getByText(/You chose an option/)).toBeVisible();
  await expect(page.getByRole("button", { name: "See your numbers" })).toHaveCount(0);

  const link = page.getByRole("link", { name: "View your numbers" });
  await expect(link).toBeVisible();
  await link.click();
  await page.waitForURL(/\/report\//);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();
});

test("AC4: a borrower with no applications sees the empty state and starts an application", async ({
  page,
}) => {
  await borrowerLogin(page, "noapp.borrower@clearquote-demo.test", password!);

  await expect(page.getByText("No application yet")).toBeVisible();
  await page.getByRole("button", { name: "Start your application" }).click();
  await page.waitForURL("/apply");
  await expect(page.getByRole("heading", { level: 1, name: "Apply" })).toBeVisible();
});

test("pending credit-check consent shows a task banner linking to the CQ-033 stub", async ({
  page,
}) => {
  // CQ-028a (parallel unit) owns the "request a hard pull" endpoint that
  // would create this row for real; it isn't built yet, so this test
  // inserts the pending `consents` row directly (worker guide's E2E note).
  const applicationId = applicationIdByClientEmail("sam.reed@clearquote-demo.test");
  const databaseUrl = (process.env.DATABASE_URL ?? "").replace(
    /^postgresql\+asyncpg:\/\//,
    "postgresql://",
  );
  const pool = new Pool({ connectionString: databaseUrl });
  let consentId: string;
  try {
    const { rows } = await pool.query<{ id: string }>(
      `insert into consents (id, application_id, type, status, requested_at, expires_at)
       values (gen_random_uuid(), $1, 'hard_pull', 'pending', now(), now() + interval '14 days')
       returning id`,
      [applicationId],
    );
    consentId = rows[0].id;
  } finally {
    await pool.end();
  }

  await borrowerLogin(page, "sam.reed@clearquote-demo.test", password!);

  await expect(
    page.getByText("Your loan officer needs your permission for a credit check."),
  ).toBeVisible();
  const bannerLink = page.getByRole("link", { name: "Review and authorize" });
  await expect(bannerLink).toHaveAttribute("href", `/tasks/credit-check/${consentId}`);
  await bannerLink.click();
  await page.waitForURL(`/tasks/credit-check/${consentId}`);
  await expect(page.getByRole("heading", { level: 1, name: "Credit check" })).toBeVisible();
});

test("AC6: 375 px, no horizontal scroll, with real application cards", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await borrowerLogin(page, "priya.nair@clearquote-demo.test", password!);

  await expect(page.getByText("Your loan officer is reviewing your numbers")).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.screenshot({
    path: "docs/backlog/CQ-031-borrower-home/evidence/portal-home-375.png",
    fullPage: true,
  });
});

test("AC6: 1280 px layout", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await borrowerLogin(page, "priya.nair@clearquote-demo.test", password!);
  await expect(page.getByText("Your loan officer is reviewing your numbers")).toBeVisible();
  await page.screenshot({
    path: "docs/backlog/CQ-031-borrower-home/evidence/portal-home-1280.png",
  });
});
