import { expect, test } from "@playwright/test";

import { flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// CQ-026 spec.md AC6: filters live in the URL, survive reload and back
// navigation, and "Clear filters" resets the URL -- mirrors
// `e2e/lo-console/applications-list.spec.ts`. Needs `.env`'s
// SEED_STAFF_PASSWORD and `make demo-reset`'s seeded users/personas.
const password = process.env.SEED_STAFF_PASSWORD;
const MANAGER = "casey.nguyen@clearquote-demo.test";
const EVIDENCE = "docs/backlog/CQ-026-clients/evidence";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

test("filter bar, sortable table and pagination render for a Manager", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);

  await page.goto("/clients");
  await expect(page.getByRole("heading", { level: 1, name: "Clients" })).toBeVisible();
  await expect(page.getByLabel("Search")).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "Active" })).toBeVisible();
  // Manager/Admin only (spec.md "Frontend").
  await expect(page.getByLabel("LO")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear filters" })).toBeVisible();

  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Clients pagination" })).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE}/clients-list.png` });
});

test("a search filter updates the URL and survives reload and back navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);
  await page.goto("/clients");

  await page.getByLabel("Search").fill("hale");
  await expect(page).toHaveURL(/q=hale/);
  await expect(page.getByText("Marcus Hale")).toBeVisible();

  // AC6: reload restores the same filtered table from the URL alone.
  await page.reload();
  await expect(page).toHaveURL(/q=hale/);
  await expect(page.getByText("Marcus Hale")).toBeVisible();

  // AC6: change a filter, then back-navigate to the prior URL/state.
  await page.getByRole("radio", { name: "Active only" }).click();
  await expect(page).toHaveURL(/has_active=true/);
  await page.goBack();
  await expect(page).toHaveURL(/q=hale/);
  await expect(page).not.toHaveURL(/has_active=true/);
});

test("Clear filters resets the URL to a bare /clients", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);
  await page.goto("/clients?q=hale&has_active=true");

  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/clients$/);
});

test("clicking a row opens the client detail page", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, MANAGER, password!);
  await page.goto("/clients?q=hale");

  await page.getByText("Marcus Hale").click();
  await page.waitForURL(/\/clients\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: "Marcus Hale" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Applications" })).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "Quotes sent", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Activity" })).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE}/client-detail.png` });
});
