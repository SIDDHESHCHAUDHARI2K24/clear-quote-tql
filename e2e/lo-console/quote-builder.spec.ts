import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// CQ-018 spec.md acceptance criteria against the real stack (API + worker +
// LO console) and seeded personas (`make demo-reset`).
const staffPassword = process.env.SEED_STAFF_PASSWORD;
test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

const LO_EMAIL = "jordan.lee@clearquote-demo.test"; // owns Marcus Hale and Aisha Coleman
const MANAGER_EMAIL = "casey.nguyen@clearquote-demo.test"; // sees every LO's applications
const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-018-quote-builder/evidence");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

async function openPricing(page: Page, email: string, clientEmail: string) {
  const applicationId = applicationIdByClientEmail(clientEmail);
  await staffLogin(page, email, staffPassword!);
  await page.goto(`/applications/${applicationId}/pricing`);
  const builder = page.getByRole("region", { name: "Quote builder" });
  await expect(builder).toBeVisible();
  return { applicationId, builder };
}

function rateOf(text: string): number {
  const match = /(\d+\.\d{3})%/.exec(text);
  if (!match) throw new Error(`no rate in ${text}`);
  return Number(match[1]);
}

test("AC1: Marcus Hale shows 4 quotes in 2 groups with no user action", async ({ page }) => {
  const { builder } = await openPricing(page, LO_EMAIL, "marcus.hale@clearquote-demo.test");
  const groups = builder.getByTestId("quote-group");
  await expect(groups).toHaveCount(2);
  await expect(groups.nth(0).getByRole("heading")).toHaveText("At DSCR 1.00");
  await expect(groups.nth(1).getByRole("heading")).toHaveText(/^At your DSCR \(0\.\d\d\)$/);
  await expect(builder.getByRole("article")).toHaveCount(4);
  await expect(builder.getByRole("article", { name: "Buydown quote" })).toHaveCount(2);
  await page.setViewportSize({ width: 1440, height: 1800 });
  await builder.screenshot({ path: path.join(EVIDENCE_DIR, "ac1-marcus-groups.png") });
});

test("AC5: starring a quote recommends it and the header note rate follows", async ({ page }) => {
  const { builder } = await openPricing(page, LO_EMAIL, "marcus.hale@clearquote-demo.test");
  const noteRate = page
    .locator("dt", { hasText: "Note rate" })
    .locator("xpath=following-sibling::dd");

  const buydown = builder
    .getByTestId("quote-group")
    .nth(0)
    .getByRole("article", { name: "Buydown quote" });
  const rate = rateOf(await buydown.innerText());
  await buydown.getByRole("button", { name: /^Recommend Buydown/ }).click();
  await expect(buydown.getByRole("button", { name: /is recommended$/ })).toBeVisible();
  await expect(noteRate).toHaveText(`${rate.toFixed(3)}%`);
  await expect(builder.getByRole("button", { pressed: true })).toHaveCount(1);

  const par = builder.getByTestId("quote-group").nth(0).getByRole("article", { name: "Par quote" });
  const parRate = rateOf(await par.innerText());
  await par.getByRole("button", { name: /^Recommend Par/ }).click();
  await expect(noteRate).toHaveText(`${parRate.toFixed(3)}%`);
  await expect(builder.getByRole("button", { pressed: true })).toHaveCount(1);
});

test("AC3: editing to 25% down and Save & AutoQuote replaces that scenario's par and buydown", async ({
  page,
}) => {
  const { builder } = await openPricing(page, LO_EMAIL, "marcus.hale@clearquote-demo.test");
  const group = builder.getByTestId("quote-group").nth(1);
  const oldPar = group.getByRole("article", { name: "Par quote" });
  const oldParRate = rateOf(await oldPar.innerText());
  const oldIds = await group
    .getByRole("article")
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-priced-at")));

  await group.getByRole("button", { name: "Edit scenario" }).click();
  const dialog = page.getByRole("dialog");
  const down = dialog.getByLabel("Down payment percent");
  await down.fill("25");
  await expect(dialog.getByLabel("Preview cash to close")).not.toHaveText("—");
  await dialog.getByRole("button", { name: "Save & AutoQuote" }).click();
  await expect(dialog).toBeHidden({ timeout: 15000 });

  await expect(group.getByRole("article")).toHaveCount(2);
  const newPar = group.getByRole("article", { name: "Par quote" });
  await expect(group.getByRole("article", { name: "Buydown quote" })).toBeVisible();
  const newPricedAt = await group
    .getByRole("article")
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-priced-at")));
  expect(newPricedAt).not.toEqual(oldIds);
  expect(rateOf(await newPar.innerText())).toBeLessThanOrEqual(oldParRate);
  await builder.screenshot({ path: path.join(EVIDENCE_DIR, "ac3-marcus-25-down.png") });
});

test("AC4: Choose manually lists >= 8 products; a pick becomes a card; delete removes it", async ({
  page,
}) => {
  const { builder } = await openPricing(page, LO_EMAIL, "marcus.hale@clearquote-demo.test");
  const group = builder.getByTestId("quote-group").nth(0);
  await group.getByRole("button", { name: "Edit scenario" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Choose manually" }).click();

  const grid = page.getByRole("table", { name: "Priced products" });
  await expect(grid).toBeVisible({ timeout: 15000 });
  const rows = grid.getByTestId("product-row");
  expect(await rows.count()).toBeGreaterThanOrEqual(8);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "ac4-manual-grid.png") });

  const pick = rows.filter({ hasText: "Max Credit" });
  const pickText = await pick.innerText();
  await pick.getByRole("button", { name: /^Choose / }).click();
  await expect(grid).toBeHidden({ timeout: 15000 });

  const manual = group.getByRole("article", { name: "Manual quote" });
  await expect(manual).toBeVisible();
  expect(rateOf(await manual.innerText())).toBe(rateOf(pickText));
  await expect(manual).toContainText("-1.500%");

  await manual.getByRole("button", { name: /^Delete Manual/ }).click();
  await expect(group.getByRole("article", { name: "Manual quote" })).toHaveCount(0);
});

test("AC6: Aisha Coleman's Save & AutoQuote shows 'Cannot price: missing Occupancy' and creates nothing", async ({
  page,
}) => {
  const { applicationId, builder } = await openPricing(
    page,
    LO_EMAIL,
    "aisha.coleman@clearquote-demo.test",
  );
  await builder.getByRole("button", { name: "Add scenario" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Purchase price").fill("300000");
  await dialog.getByLabel("Down payment percent").fill("25");
  await dialog.getByRole("button", { name: "Save & AutoQuote" }).click();

  const alert = dialog.getByRole("alert");
  await expect(alert).toHaveText(/Cannot price: missing Occupancy/);
  await expect(alert.getByRole("link")).toHaveAttribute(
    "href",
    `/applications/${applicationId}/property`,
  );
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "ac6-aisha-missing-occupancy.png") });
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(builder.getByRole("article")).toHaveCount(0);
});

test("AC7: Priya Nair's primary cards carry no DSCR text; Daniel Ortiz's second group removes MI", async ({
  page,
}) => {
  const { builder } = await openPricing(page, MANAGER_EMAIL, "priya.nair@clearquote-demo.test");
  await expect(builder.getByRole("article").first()).toBeVisible();
  await expect(builder).not.toContainText(/DSCR|cashflow|prepay/i);
  await builder.screenshot({ path: path.join(EVIDENCE_DIR, "ac7-priya-primary.png") });

  const daniel = applicationIdByClientEmail("daniel.ortiz@clearquote-demo.test");
  await page.goto(`/applications/${daniel}/pricing`);
  const headings = page.getByRole("region", { name: "Quote builder" }).getByRole("heading", {
    level: 3,
  });
  await expect(headings).toHaveText(["At 5% down", "At 20% down"]);
});

test("Compare: two cards side by side with the borrower table's rows", async ({ page }) => {
  const { builder } = await openPricing(page, LO_EMAIL, "marcus.hale@clearquote-demo.test");
  const boxes = builder.getByRole("checkbox");
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await builder.getByRole("button", { name: "Compare (2)" }).click();
  const table = page.getByRole("dialog").getByRole("table");
  await expect(table.getByRole("rowheader")).toHaveText([
    "Rate",
    "Points",
    "Down payment",
    "Prepayment penalty",
    "Monthly payment",
    "Cash to close",
    "Monthly cashflow",
    "DSCR",
  ]);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "compare-marcus.png") });
});
