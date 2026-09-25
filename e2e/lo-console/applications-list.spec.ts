import { expect, test, type Page } from "@playwright/test";

import { flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

/**
 * `ApplicationsFilterBar`'s own root -- the filter bar's `Status`
 * `MultiSelect` trigger and `ApplicationsTable`'s sortable `Status` column
 * header button both have an accessible name starting with "Status", so
 * every locator that means the filter goes through this scope instead of
 * `page.getByRole("button", { name: /^Status/ })` directly.
 */
function applicationsFilterBar(page: Page) {
  return page
    .getByLabel("Search")
    .locator(
      "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' rounded-md ')]",
    );
}

// CQ-027 spec.md AC6: filters live in the URL, survive reload and back
// navigation, and "Clear filters" resets the URL. Needs `.env`'s
// SEED_STAFF_PASSWORD and `make demo-reset`'s seeded users/personas.
const password = process.env.SEED_STAFF_PASSWORD;
const MANAGER = "casey.nguyen@clearquote-demo.test";
const EVIDENCE = "docs/backlog/CQ-027-applications-list/evidence";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

test("filter bar, sortable table and pagination render for a Manager", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);

  await page.goto("/applications");
  await expect(page.getByRole("heading", { level: 1, name: "Applications" })).toBeVisible();
  await expect(page.getByLabel("Search")).toBeVisible();
  // Scoped to the filter bar -- `ApplicationsTable`'s sortable "Status"
  // column header is also a `button` named "Status", so an unscoped
  // `getByRole("button", { name: /^Status/ })` is a strict-mode violation
  // (two matches) once the table has rows.
  const filterBar = applicationsFilterBar(page);
  await expect(filterBar.getByRole("button", { name: /^Status/ })).toBeVisible();
  await expect(page.getByRole("group", { name: "Strategy" })).toBeVisible();
  await expect(page.getByLabel("State")).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "Property" })).toBeVisible();
  // Manager/Admin only (spec.md "Frontend").
  await expect(page.getByLabel("LO")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear filters" })).toBeVisible();

  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Applications pagination" })).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE}/applications-list.png` });
});

test("a status filter updates the URL and survives reload and back navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);
  await page.goto("/applications");

  // The seed has 26 NeedsAttention rows (24 background + Aisha + Ben), so
  // Aisha alone isn't guaranteed onto page 1 -- add the search filter too
  // (AC1's "three combined filters") to make the result deterministic.
  await page.getByLabel("Search").fill("aisha");
  await applicationsFilterBar(page)
    .getByRole("button", { name: /^Status/ })
    .click();
  // A plain `.click()`, not `.check()`: the checkbox is fully controlled by
  // the URL (no local state), so it only reflects `checked` once
  // `router.push` round-trips -- `.check()`'s own post-click assertion
  // races that.
  await page.getByRole("checkbox", { name: "Needs attention" }).click();
  await page.keyboard.press("Escape");

  await expect(page).toHaveURL(/status=needs_attention/);
  await expect(page).toHaveURL(/q=aisha/);
  await expect(page.getByText("Aisha Coleman")).toBeVisible();

  // AC6: reload restores the same filtered table from the URL alone.
  await page.reload();
  await expect(page).toHaveURL(/status=needs_attention/);
  await expect(page.getByText("Aisha Coleman")).toBeVisible();

  // AC6: change a filter, then back-navigate to the prior URL/state.
  await page.getByLabel("State").selectOption("FL");
  await expect(page).toHaveURL(/state=FL/);
  await page.goBack();
  await expect(page).toHaveURL(/status=needs_attention/);
  await expect(page).not.toHaveURL(/state=FL/);
});

test("Clear filters resets the URL to a bare /applications", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);
  await page.goto("/applications?status=priced&state=FL");

  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/applications$/);
});

test("a dashboard-style tile link (?status=NeedsAttention) is accepted", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);

  await page.goto("/applications?status=NeedsAttention&q=aisha");
  await expect(page.getByText("Aisha Coleman")).toBeVisible();
});

test("clicking a row opens the workspace", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);
  await page.goto("/applications?status=NeedsAttention&q=aisha");

  await page.getByText("Aisha Coleman").click();
  await page.waitForURL(/\/applications\/[0-9a-f-]{36}$/);
});
