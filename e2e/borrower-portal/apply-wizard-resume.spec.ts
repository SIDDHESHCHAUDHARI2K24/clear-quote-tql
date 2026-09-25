import { expect, test } from "@playwright/test";

import { borrowerLogin } from "../helpers/borrowerLogin";
import { flushLoginRateLimit } from "../helpers/db";

// CQ-032 spec.md AC3: "Refreshing mid-tab 3 restores all entered values
// and returns to tab 3." Uses the P5/P6 foundation's seeded borrower with
// no application yet (`noapp.borrower@clearquote-demo.test`) so this spec
// starts from a fresh draft without needing a new signup.
const email = "noapp.borrower@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");

test("refreshing mid-tab-3 resumes at tab 3 with the entered values restored", async ({ page }) => {
  flushLoginRateLimit();
  await borrowerLogin(page, email, password!);

  await page.goto("/apply");
  await expect(page.getByRole("heading", { name: "You", exact: true })).toBeVisible();

  // -- Tab 1: just enough to validate ------------------------------------
  await page.getByLabel("First name").fill("Nadia");
  await page.getByLabel("Last name").fill("Noapp");
  await page.getByLabel("Cell phone").fill("8135550199");
  await page.getByLabel("Date of birth").fill("1990-01-15");
  await page.getByLabel("Social Security number").fill("321-45-6789");
  await page.getByLabel("Marital status").selectOption("unmarried");
  await page.getByLabel("Dependents").fill("0");
  await page.getByLabel("Street address").fill("10 Lake Ave");
  await page.getByLabel("City").fill("Lakeland");
  await page.getByLabel("State").fill("FL");
  await page.getByLabel("ZIP").fill("33801");
  await page.getByLabel("Own or rent", { exact: true }).selectOption("rent");
  await page.getByLabel("Years there").fill("3");
  await page.getByLabel("Months there").fill("2");
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 2: just enough to validate -- primary occupancy, so tab 3's
  // income fields are actually required (this is what keeps tab 3
  // genuinely incomplete below, for a true "mid-tab" resume). ------------
  await expect(page.getByLabel("What's this loan for?")).toBeVisible();
  await page.getByLabel("What's this loan for?").selectOption("primary");
  await page.getByLabel("Do you have a property in mind?").selectOption("no");
  await page.getByRole("button", { name: /^States/ }).click();
  await page.getByLabel("FL", { exact: true }).check();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Metros/ }).click();
  await page.getByLabel("Tampa, FL").check();
  await page.keyboard.press("Escape");
  await page.getByLabel("Target price").fill("350000");
  await page.getByLabel("Down payment").selectOption("0.20");
  await page.getByRole("button", { name: "Next", exact: true }).click();

  // -- Tab 3: a quick Back within the 1 s debounce must not drop the
  // pending edit (CQ-032b review round 1). Type something, click Back
  // immediately -- well before the debounce would fire on its own -- then
  // come forward again and confirm it actually reached the server.
  await expect(page.getByRole("heading", { name: "Income" })).toBeVisible();
  await page.getByLabel("Employer", { exact: true }).fill("Quick Co");
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page.getByLabel("What's this loan for?")).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Income" })).toBeVisible();
  await expect(page.getByLabel("Employer", { exact: true })).toHaveValue("Quick Co");

  // -- Tab 3: type, let the 1s autosave commit, then refresh mid-tab -----
  // `monthly_income` is left blank on purpose: income is required for a
  // primary residence (spec.md AC2), so the tab stays incomplete and
  // `current_tab` stays "income" after the save -- a genuine "mid-tab 3"
  // resume, not one that already jumped ahead to tab 4.
  await expect(page.getByRole("heading", { name: "Income" })).toBeVisible();
  await page.getByLabel("Employer", { exact: true }).fill("Sunshine Realty");
  await page.getByLabel("Years employed", { exact: true }).fill("2");
  await page.getByLabel("Monthly debts", { exact: true }).fill("300");
  await page.getByLabel("Liquid assets").fill("95000");

  // spec.md: "Autosave 1 s after the last change" -- wait past the
  // debounce so the values are actually persisted before refreshing.
  await page.waitForTimeout(1500);
  await expect(page.getByText("Saved")).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Income" })).toBeVisible();
  await expect(page.getByLabel("Employer", { exact: true })).toHaveValue("Sunshine Realty");
  await expect(page.getByLabel("Years employed", { exact: true })).toHaveValue("2");
  await expect(page.getByLabel("Monthly debts", { exact: true })).toHaveValue("300");
  await expect(page.getByLabel("Liquid assets")).toHaveValue("95000");
});
