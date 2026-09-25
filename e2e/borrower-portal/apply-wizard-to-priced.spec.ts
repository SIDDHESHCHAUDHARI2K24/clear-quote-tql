import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { closeDbPool } from "../helpers/db";
import { portalApiBaseUrl } from "../helpers/env";
import { readOtpCode } from "../helpers/mailpit";

// CQ-032 spec.md AC1: a new borrower signs up (OTP from Mailpit),
// completes the four-tab wizard for a Tampa STR purchase and submits; the
// application then flows through CQ-011's pipeline (needs `make worker`
// on this slot's queue, per the worker guide's E2E recipe) to Priced with
// no LO action. Priced is observed the same way AC1's plan.md test does
// it on the API side, but from the borrower's own side: home's `stage`
// flips from "applied" ("Application received", spec.md) to "in_review"
// once the application is priced (`portal/home/service.py::stage_and_
// label` maps `ApplicationStatus.PRICED` -> `PortalStage.IN_REVIEW`).
const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-032-apply-wizard/evidence");

test.describe.configure({ mode: "serial" });

test.afterAll(async () => {
  await closeDbPool();
});

test("a new borrower applies for a Tampa STR purchase and the application reaches Priced", async ({
  page,
}) => {
  // The pipeline poll below waits for a real Temporal worker run (verify
  // -> enrich -> validate -> price), well past Playwright's default 30s.
  test.setTimeout(150_000);
  const stamp = Date.now().toString(36);
  const email = `e2e.apply.${stamp}@example.com`;
  const password = "Sup3r-secret-pass!1";

  // -- Sign up (AC1: "with the OTP from Mailpit") ---------------------
  await page.goto("/signup");
  await page.getByLabel("Full name").fill("Tina Tampa");
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

  // -- Tab 1: You -------------------------------------------------------
  await expect(page.getByRole("heading", { name: "You", exact: true })).toBeVisible();

  // AC8: every field has a label and no critical/serious a11y violations.
  const axeResults = await new AxeBuilder({ page }).analyze();
  const blocking = axeResults.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);

  // spec.md: "The 375 px layout has no horizontal scroll." Check at 375,
  // then switch back to 1280 for the rest of the run (E2E recipe: 1280 px
  // + 375 px for portal pages).
  await page.setViewportSize({ width: 375, height: 812 });
  const overflowsHorizontally = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflowsHorizontally).toBe(false);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-tab1-you-375.png") });
  await page.setViewportSize({ width: 1280, height: 800 });

  await page.getByLabel("First name").fill("Tina");
  await page.getByLabel("Last name").fill("Tampa");
  expect(await page.getByLabel("Email").inputValue()).toBe(email);
  await page.getByLabel("Cell phone").fill("8135550142");
  await page.getByLabel("Date of birth").fill("1988-04-12");
  await page.getByLabel("Social Security number").fill("123-45-6789");
  await page.getByLabel("Marital status").selectOption("unmarried");
  await page.getByLabel("Dependents").fill("0");
  await page.getByLabel("Street address").fill("22 River Rd");
  await page.getByLabel("City").fill("Lakeland");
  await page.getByLabel("State").fill("FL");
  await page.getByLabel("ZIP").fill("33801");
  await page.getByLabel("Own or rent", { exact: true }).selectOption("rent");
  await page.getByLabel("Years there").fill("3");
  await page.getByLabel("Months there").fill("2");
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-tab1-you-1280.png") });
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 2: Property & goal --------------------------------------------
  await expect(page.getByLabel("What's this loan for?")).toBeVisible();
  await page.getByLabel("What's this loan for?").selectOption("str");
  await page.getByLabel("Do you have a property in mind?").selectOption("no");

  // AC8, custom widgets: the two-tier states/metros `MultiSelect` picker.
  const propertyAxe = await new AxeBuilder({ page }).analyze();
  const propertyBlocking = propertyAxe.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(propertyBlocking, JSON.stringify(propertyBlocking, null, 2)).toEqual([]);

  await page.getByRole("button", { name: /^States/ }).click();
  await page.getByLabel("FL", { exact: true }).check();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Metros/ }).click();
  await page.getByLabel("Tampa, FL").check();
  await page.keyboard.press("Escape");
  await page.getByLabel("Target price").fill("400000");
  await page.getByLabel("Down payment").selectOption("0.25");
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-tab2-property-1280.png") });
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 3: Income & assets --------------------------------------------
  await expect(page.getByRole("heading", { name: "Income" })).toBeVisible();
  await page.getByLabel("Monthly debts (optional)").fill("450");
  await page.getByLabel("Liquid assets").fill("180000");
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-tab3-income-1280.png") });
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 4: Consent -----------------------------------------------------
  await expect(page.getByRole("heading", { name: "Consent" })).toBeVisible();
  await page.getByLabel(/soft credit pull/).check();
  await page.getByLabel(/be contacted about my application/).check();
  await page.getByLabel(/agree to the terms/).check();
  await page.getByLabel("Type your full name to sign").fill("Tina Tampa");
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-tab4-consent-1280.png") });
  await page.getByRole("button", { name: "Submit application" }).click();

  await expect(page.getByRole("heading", { name: "Application submitted" })).toBeVisible();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-confirmation-1280.png") });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-confirmation-375.png") });

  await page.getByRole("button", { name: "Go to your home" }).click();
  await page.waitForURL("/");
  await expect(page.getByText("Application received")).toBeVisible();

  // -- Poll for Priced (AC1) -- `make worker` must be running on this
  // slot's Temporal queue (E2E_NOTE / worker guide "E2E recipe").
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
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "apply-priced-home-375.png") });
});
