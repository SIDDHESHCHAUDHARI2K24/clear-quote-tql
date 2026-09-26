import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, closeDbPool, flushLoginRateLimit } from "../helpers/db";
import { portalApiBaseUrl } from "../helpers/env";
import { readOtpCode } from "../helpers/mailpit";
import { staffLogin } from "../helpers/staffLogin";

// P6 milestone (docs/backlog/phase-p5-p6-plan.md "Verification (phase
// level)"): "a new borrower's application flows to Intake and auto-prices
// (CQ-032 AC1), Playwright against slot 0 with the worker running." This
// spec's own job is the cross-app half CQ-032's own AC1 test
// (`apply-wizard-to-priced.spec.ts`) never checks: that the LO console --
// a second browser context, a different app entirely -- shows the exact
// same application at Priced with no LO having touched it. The sign-up +
// four-tab wizard steps below are the same known-good path
// `apply-wizard-to-priced.spec.ts` already proved (CQ-032 AC1: STR
// purchase, Tampa FL, no property in hand yet), reused here rather than
// re-derived, minus that item's own a11y/viewport assertions (already
// covered there) so this milestone stays focused on the cross-app claim.
//
// Needs `.env`'s SEED_STAFF_PASSWORD, `make demo-reset`, and a running
// API + `make worker` on this worktree's slot (the pipeline runs for
// real, with no LO action).
const staffPassword = process.env.SEED_STAFF_PASSWORD;
const MANAGER = "casey.nguyen@clearquote-demo.test";
// This project (`cross-app`, playwright.config.ts) has no `baseURL` of its
// own -- every context below is opened with an explicit `baseURL`, same as
// borrower-action-reflects-in-console.spec.ts.
const LO_BASE_URL = process.env.LO_BASE_URL ?? "http://localhost:3010";
const PORTAL_BASE_URL = process.env.PORTAL_BASE_URL ?? "http://localhost:3020";
const EVIDENCE_DIR = "docs/backlog/evidence/p56-phase";

test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.afterAll(async () => {
  await closeDbPool();
});

test("P6 milestone: a new borrower applies, reaches Intake, auto-prices, and the LO console shows Priced with no LO action", async ({
  browser,
}) => {
  // The pipeline poll below waits for a real Temporal worker run (verify
  // -> enrich -> validate -> price), well past Playwright's default 30s
  // -- same budget as apply-wizard-to-priced.spec.ts.
  test.setTimeout(150_000);
  const stamp = Date.now().toString(36);
  const email = `e2e.p6milestone.${stamp}@example.com`;
  const password = "Sup3r-secret-pass!1";

  const portalContext = await browser.newContext({ baseURL: PORTAL_BASE_URL });
  const page = await portalContext.newPage();

  // -- Sign up (OTP from Mailpit) -----------------------------------------
  await page.goto("/signup");
  await page.getByLabel("Full name").fill("Milo Milestone");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByLabel("Verification code")).toBeVisible();
  const otp = await readOtpCode(email);
  await page.getByLabel("Verification code").fill(otp);
  await page.getByRole("button", { name: "Verify" }).click();
  await page.waitForURL("/");

  await page.getByRole("button", { name: "Start your application" }).click();
  await page.waitForURL("/apply");

  // -- Tab 1: You -----------------------------------------------------------
  await expect(page.getByRole("heading", { name: "You", exact: true })).toBeVisible();
  await page.getByLabel("First name").fill("Milo");
  await page.getByLabel("Last name").fill("Milestone");
  await page.getByLabel("Cell phone").fill("8135550143");
  await page.getByLabel("Date of birth").fill("1988-04-12");
  await page.getByLabel("Social Security number").fill("123-45-6781");
  await page.getByLabel("Marital status").selectOption("unmarried");
  await page.getByLabel("Dependents").fill("0");
  await page.getByLabel("Street address").fill("23 River Rd");
  await page.getByLabel("City").fill("Lakeland");
  await page.getByLabel("State").fill("FL");
  await page.getByLabel("ZIP").fill("33801");
  await page.getByLabel("Own or rent", { exact: true }).selectOption("rent");
  await page.getByLabel("Years there").fill("3");
  await page.getByLabel("Months there").fill("2");
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 2: Property & goal -----------------------------------------------
  await expect(page.getByLabel("What's this loan for?")).toBeVisible();
  await page.getByLabel("What's this loan for?").selectOption("str");
  await page.getByLabel("Do you have a property in mind?").selectOption("no");
  await page.getByRole("button", { name: /^States/ }).click();
  await page.getByLabel("FL", { exact: true }).check();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Metros/ }).click();
  await page.getByLabel("Tampa, FL").check();
  await page.keyboard.press("Escape");
  await page.getByLabel("Target price").fill("400000");
  await page.getByLabel("Down payment").selectOption("0.25");
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 3: Income & assets -------------------------------------------------
  await expect(page.getByRole("heading", { name: "Income" })).toBeVisible();
  await page.getByLabel("Monthly debts (optional)").fill("450");
  await page.getByLabel("Liquid assets").fill("180000");
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 4: Consent -----------------------------------------------------
  await expect(page.getByRole("heading", { name: "Consent" })).toBeVisible();
  await page.getByLabel(/soft credit pull/).check();
  await page.getByLabel(/be contacted about my application/).check();
  await page.getByLabel(/agree to the terms/).check();
  await page.getByLabel("Type your full name to sign").fill("Milo Milestone");
  await page.getByRole("button", { name: "Submit application" }).click();

  await expect(page.getByRole("heading", { name: "Application submitted" })).toBeVisible();
  await page.getByRole("button", { name: "Go to your home" }).click();
  await page.waitForURL("/");

  // -- Reaches Intake with no LO action -----------------------------------
  await expect(page.getByText("Application received")).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE_DIR}/p6-milestone-borrower-intake.png` });

  // -- Auto-prices (CQ-011's pipeline, no LO action) -----------------------
  const apiBaseUrl = portalApiBaseUrl();
  let stage: string | undefined;
  for (let attempt = 0; attempt < 90; attempt += 1) {
    const response = await page.request.get(`${apiBaseUrl}/api/v1/portal/me`);
    const body = await response.json();
    stage = body.applications?.[0]?.stage;
    if (stage && stage !== "applied") break;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  expect(stage, "application should leave the 'applied' stage once priced").not.toBe("applied");
  expect(stage).toBe("in_review");

  await page.reload();
  await expect(page.getByText("Your loan officer is reviewing your numbers")).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE_DIR}/p6-milestone-borrower-priced.png` });

  // -- Cross-app: the LO console (a second browser context, its own app)
  // shows the very same application at Priced, with no LO having opened
  // it -- least-loaded auto-assignment (E15) picks whichever LO, so this
  // signs in as the Manager, who sees every file regardless of `lo_id`. --
  const applicationId = applicationIdByClientEmail(email);
  const loContext = await browser.newContext({ baseURL: LO_BASE_URL });
  const loPage = await loContext.newPage();
  flushLoginRateLimit();
  await staffLogin(loPage, MANAGER, staffPassword!);
  await loPage.goto(`/applications/${applicationId}`);
  await loPage.waitForURL(new RegExp(`applications/${applicationId}/\\w+`));
  await expect(loPage.getByText("Priced", { exact: true })).toBeVisible();
  await loPage.screenshot({ path: `${EVIDENCE_DIR}/p6-milestone-lo-console-priced.png` });

  await loContext.close();
  await portalContext.close();
});
