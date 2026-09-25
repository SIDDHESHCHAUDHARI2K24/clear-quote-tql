import path from "node:path";

import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, execSql, flushLoginRateLimit } from "../helpers/db";
import { loConsoleApiBaseUrl } from "../helpers/env";
import { staffLogin } from "../helpers/staffLogin";

// spec.md CQ-016 acceptance criteria, against a real running stack (API +
// worker + LO console) and real seeded personas (`make demo-reset`).
// SEED_STAFF_PASSWORD must be set (see e2e/lo-console/staff-login.spec.ts).
const staffPassword = process.env.SEED_STAFF_PASSWORD;
test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

const JORDAN_EMAIL = "jordan.lee@clearquote-demo.test";
const MANAGER_EMAIL = "casey.nguyen@clearquote-demo.test";

const EVIDENCE_DIR = path.resolve(
  __dirname,
  "../../docs/backlog/CQ-016-application-workspace/evidence",
);

test.describe.configure({ mode: "serial" }); // distinct personas per test, but keep DB lookups predictable

test.beforeEach(() => {
  // Several tests in this file do a real staff login; without this, the
  // combined attempt count across the whole file can trip the staff login
  // endpoint's own rate limit well before any individual test's limit
  // would matter on its own (see `flushLoginRateLimit`'s docstring).
  flushLoginRateLimit();
});

test("AC4: Aisha Coleman (missing occupancy) opens on her first flagged tab with a red badge", async ({
  page,
}) => {
  const applicationId = applicationIdByClientEmail("aisha.coleman@clearquote-demo.test");
  await staffLogin(page, JORDAN_EMAIL, staffPassword!);

  await page.goto(`/applications/${applicationId}`);
  await page.waitForURL(`**/applications/${applicationId}/pricing`);

  const pricingTab = page.getByRole("tab", { name: /pricing/i });
  await expect(pricingTab).toHaveAttribute("aria-selected", "true");
  const badge = pricingTab.getByLabel(/\d+ flags?/);
  await expect(badge).toBeVisible();
  await expect(badge).toHaveText(/[1-9]\d*/);
});

test("AC4: Ben Ford's Housing tab shows a red badge and is the default tab", async ({ page }) => {
  const applicationId = applicationIdByClientEmail("ben.ford@clearquote-demo.test");
  await staffLogin(page, MANAGER_EMAIL, staffPassword!); // Ben Ford belongs to the other seeded LO

  await page.goto(`/applications/${applicationId}`);
  await page.waitForURL(`**/applications/${applicationId}/housing`);

  const housingTab = page.getByRole("tab", { name: /housing/i });
  await expect(housingTab).toHaveAttribute("aria-selected", "true");
  await expect(housingTab.getByLabel(/\d+ flags?/)).toBeVisible();
});

test("AC2: Priya Nair (primary) opens on Pricing with no PPP field", async ({ page }) => {
  const applicationId = applicationIdByClientEmail("priya.nair@clearquote-demo.test");
  await staffLogin(page, JORDAN_EMAIL, staffPassword!);

  await page.goto(`/applications/${applicationId}`);
  await page.waitForURL(`**/applications/${applicationId}/pricing`);

  await expect(page.getByText("Priya Nair")).toBeVisible();
  await expect(page.getByRole("tab", { name: /pricing/i })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByText("PPP")).not.toBeVisible();
  await expect(page.getByText("Purchasing power")).toBeVisible();
});

test("AC8: the header stays visible while scrolling, at 1280px and 1440px", async ({ page }) => {
  const applicationId = applicationIdByClientEmail("priya.nair@clearquote-demo.test");
  await staffLogin(page, JORDAN_EMAIL, staffPassword!);
  await page.goto(`/applications/${applicationId}`);
  await page.waitForURL(`**/applications/${applicationId}/pricing`);

  for (const width of [1280, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    await expect(page.getByText("Priya Nair")).toBeVisible();
    await page.mouse.wheel(0, 600);
    await expect(page.getByText("Priya Nair")).toBeInViewport();
    await page.screenshot({ path: path.join(EVIDENCE_DIR, `header-${width}.png`) });
  }
});

// Withdrawn is terminal (`patch_application_status` 409s on any further
// PATCH from a non-terminal status), and only `applications.status` itself
// changes (plus one activity event) -- but leaving Sam Reed withdrawn
// leaks into `portal-home.spec.ts`'s later "pending credit-check consent"
// test, which needs his application still active (a `stage is
// PortalStage.CLOSED` application always gets `next_action = NONE`, so the
// pending consent it inserts for him would never render a banner).
// Restore his original seeded status (seed/personas/p05_sam_reed.yaml:
// `pipeline_end_status: priced`) directly -- there's no "un-withdraw"
// endpoint, since that's not a real product flow. In `afterAll`, not
// inline at the end of the test body (review finding): a failed/timed-out
// assertion between the withdraw click and the end of the test would
// otherwise skip this restore and leave Sam Reed withdrawn for every
// later run until a fresh `make demo-reset`.
test.afterAll(() => {
  const applicationId = applicationIdByClientEmail("sam.reed@clearquote-demo.test");
  execSql(`update applications set status = 'priced' where id = '${applicationId}';`);
});

test("AC6: withdrawing an application sets status Withdrawn and hides the actions menu", async ({
  page,
}) => {
  const applicationId = applicationIdByClientEmail("sam.reed@clearquote-demo.test"); // Jordan's
  await staffLogin(page, JORDAN_EMAIL, staffPassword!);
  await page.goto(`/applications/${applicationId}`);
  await page.waitForURL(new RegExp(`applications/${applicationId}/\\w+`));

  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("menuitem", { name: "Withdraw application" }).click();
  await page.getByLabel(/Reason/).fill("E2E test withdrawal");
  await page.getByRole("button", { name: "Confirm" }).click();

  await expect(page.getByText("Withdrawn")).toBeVisible();
  await expect(page.getByRole("button", { name: "Actions" })).not.toBeVisible();
});

test("AC5: an LO requesting another LO's application gets the not-found page; a Manager can open it", async ({
  page,
}) => {
  const applicationId = applicationIdByClientEmail("ben.ford@clearquote-demo.test");

  await staffLogin(page, JORDAN_EMAIL, staffPassword!); // does not own Ben Ford
  await page.goto(`/applications/${applicationId}`);
  await expect(page.getByRole("heading", { name: "Application not found" })).toBeVisible();

  // A fresh session: `middleware.ts` redirects an already-signed-in
  // request away from /login, so Jordan's cookie must go first.
  await page.context().clearCookies();
  await staffLogin(page, MANAGER_EMAIL, staffPassword!);
  await page.goto(`/applications/${applicationId}`);
  await page.waitForURL(`**/applications/${applicationId}/housing`);
  await expect(page.getByText("Ben Ford")).toBeVisible();
});

test("AC7: the pipeline banner shows the running stage while the workflow is active", async ({
  page,
}) => {
  const applicationId = applicationIdByClientEmail("marcus.hale@clearquote-demo.test");
  const apiBaseUrl = loConsoleApiBaseUrl();
  await staffLogin(page, JORDAN_EMAIL, staffPassword!);

  // Runs in the browser (not Playwright's separate `request` fixture) so
  // the already-signed-in `cq_staff_session` cookie is sent automatically
  // (it's set for the `localhost` domain, not scoped to the LO console's
  // own port) -- `POST .../pipeline/start` (CQ-011) is idempotent, so this
  // is safe even if a prior run of this spec already started it. It
  // returns as soon as the workflow is accepted, before the worker has
  // necessarily run its first activity, so this also waits (still inside
  // the browser, polling the same summary endpoint the app itself calls)
  // until `last_pipeline_stage` actually flips non-null -- otherwise the
  // page's first paint could race ahead of the worker, see `last_pipeline_
  // stage: null` (which `WorkspaceProvider` correctly treats as terminal --
  // nothing to poll for) and never start polling for this run. A real LO
  // never hits that race: whatever in-app action starts a pipeline (out of
  // this item's scope -- CQ-028) can just call `refetch()` itself.
  await page.evaluate(
    async ({ apiBaseUrl, applicationId }) => {
      await fetch(`${apiBaseUrl}/api/v1/applications/${applicationId}/pipeline/start`, {
        method: "POST",
        credentials: "include",
      });
      const deadline = Date.now() + 8000;
      while (Date.now() < deadline) {
        const res = await fetch(`${apiBaseUrl}/api/v1/applications/${applicationId}/summary`, {
          credentials: "include",
        });
        const body = await res.json();
        if (body.last_pipeline_stage !== null) return;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    },
    { apiBaseUrl, applicationId },
  );

  await page.goto(`/applications/${applicationId}`);
  await page.waitForURL(new RegExp(`applications/${applicationId}/\\w+`));

  await expect(page.getByRole("status").filter({ hasText: "Pipeline running" })).toBeVisible({
    timeout: 10000,
  });
});
