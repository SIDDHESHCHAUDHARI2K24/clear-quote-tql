import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// P5/P6 foundation (E5, docs/backlog/phase-p5-p6-foundation.md): the
// `(staff)` shell. Needs `.env`'s SEED_STAFF_PASSWORD and `make
// demo-reset`'s seeded staff users (seed/users.yaml).
const password = process.env.SEED_STAFF_PASSWORD;
const ADMIN = "riley.admin@clearquote-demo.test";
const LO = "jordan.lee@clearquote-demo.test";
const EVIDENCE = "docs/backlog/evidence/p56-foundation";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  // Several real staff logins in one file: reset this slot's login rate
  // limit between tests (same approach as workspace.spec.ts).
  flushLoginRateLimit();
});

async function openUserMenu(page: Page, name: RegExp) {
  await page.getByRole("button", { name }).click();
}

test("an admin sees Integrations and Settings in the user menu", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);

  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  await openUserMenu(page, /Riley/);
  await expect(page.getByText(/Signed in as .*\(Admin\)/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Integrations" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Settings" })).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE}/lo-admin-user-menu.png` });

  await page.getByRole("link", { name: "Integrations" }).click();
  await expect(page).toHaveURL(/\/admin\/integrations$/);
  await expect(page.getByRole("heading", { level: 1, name: "Integrations" })).toBeVisible();
  // CQ-029 built the real panel (was a stub when this spec was written):
  // a status row per adapter, e.g. "pricing" / "Optimal Blue".
  await expect(page.getByText("pricing")).toBeVisible();
  await expect(page.getByText("Optimal Blue")).toBeVisible();
});

test("an LO has no admin entries and is refused /admin pages", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, LO, password!);

  await openUserMenu(page, /Jordan/);
  await expect(page.getByText(/Signed in as .*\(Loan Officer\)/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Integrations" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Settings" })).toHaveCount(0);
  await page.screenshot({ path: `${EVIDENCE}/lo-user-menu.png` });

  await page.goto("/admin/settings");
  await expect(page.getByRole("heading", { name: "Not authorized" })).toBeVisible();
});

test("the nav links go to the stub pages (Dashboard is CQ-025's real page)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, LO, password!);
  const nav = page.getByRole("navigation", { name: "Main" });

  // CQ-027 (small, logged necessity): `/applications` is no longer a stub
  // -- it has no "Built in CQ-027" text -- so it carries no `item` here;
  // its own coverage is `e2e/lo-console/applications-list.spec.ts`.
  //
  // CQ-026 (small, logged necessity): `/clients` is no longer a stub
  // either -- its own coverage is `e2e/lo-console/clients-list.spec.ts`.
  for (const [label, path, item] of [["Applications", "/applications", null]] as const) {
    await nav.getByRole("link", { name: label }).click();
    await page.waitForURL(path);
    await expect(page.getByRole("heading", { level: 1, name: label })).toBeVisible();
    if (item) await expect(page.getByText(`Built in ${item}`)).toBeVisible();
    await expect(nav.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
  }

  // CQ-025 replaced the Dashboard stub -- still reachable from the nav, but
  // it's the real dashboard now (no "Built in CQ-025" stub text).
  await nav.getByRole("link", { name: "Dashboard" }).click();
  await page.waitForURL("/");
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await page.screenshot({ path: `${EVIDENCE}/lo-dashboard-stub.png` });

  // CQ-029 built the real Outbox page (was a stub when this spec was
  // written) -- still reachable from the nav, no longer "Built in CQ-029".
  await nav.getByRole("link", { name: "Outbox" }).click();
  await page.waitForURL("/outbox");
  await expect(page.getByRole("heading", { level: 1, name: "Outbox" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Outbox" })).toHaveAttribute("aria-current", "page");
});

test("sign out returns to the login page", async ({ page }) => {
  await staffLogin(page, LO, password!);
  await openUserMenu(page, /Jordan/);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
});
