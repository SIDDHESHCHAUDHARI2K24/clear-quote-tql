import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { borrowerLogin } from "../helpers/borrowerLogin";
import { flushLoginRateLimit } from "../helpers/db";

// P5/P6 foundation (E6, E17, docs/backlog/phase-p5-p6-foundation.md): the
// `(portal)` shell, signed in as the seeded no-application borrower (so no
// persona the report specs rely on is touched). Needs `.env`'s
// SEED_BORROWER_PASSWORD and `make demo-reset`.
const email = "noapp.borrower@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;
const EVIDENCE = "docs/backlog/evidence/p56-foundation";

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

async function expectNoHorizontalScroll(page: Page) {
  const [scrollWidth, clientWidth] = await Promise.all([
    page.evaluate(() => document.documentElement.scrollWidth),
    page.evaluate(() => document.documentElement.clientWidth),
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
}

test("header, nav and footer disclosures render; no horizontal scroll at 375 px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await borrowerLogin(page, email, password!);

  await expect(page.getByRole("link", { name: /TQL/ })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
  await expect(nav.getByRole("link", { name: "Support" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Account menu/ })).toBeVisible();

  const footer = page.getByRole("contentinfo");
  await expect(footer).toContainText("NMLS #");
  await expect(footer).toContainText("Equal Housing Lender");
  await expect(footer).toContainText("Not a commitment to lend");

  await expect(page.getByRole("heading", { level: 1, name: "Hi Nadia" })).toBeVisible();
  await expect(page.getByText("No application yet")).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: `${EVIDENCE}/portal-home-375.png`, fullPage: true });

  await nav.getByRole("link", { name: "Support" }).click();
  await page.waitForURL("/support");
  await expect(page.getByRole("heading", { level: 1, name: "Get in touch" })).toBeVisible();
  await expectNoHorizontalScroll(page);

  // The real pages (CQ-032, CQ-033), not the stub-era placeholders: /apply
  // renders its own "Apply" heading, and an unknown credit-check id (this
  // all-zero UUID matches no request) 404s to CreditConsent's "Request not
  // found" state (ConsentStates.tsx) rather than a per-page title.
  for (const [path, title] of [
    ["/apply", "Apply"],
    ["/tasks/credit-check/00000000-0000-0000-0000-000000000000", "Request not found"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.getByRole("contentinfo")).toContainText("Equal Housing Lender");
    await expectNoHorizontalScroll(page);
  }
});

test("desktop layout and sign out from the account menu", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await borrowerLogin(page, email, password!);
  await expect(page.getByRole("heading", { level: 1, name: "Hi Nadia" })).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE}/portal-home-1280.png` });

  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
});

test("a signed-out visit to a shell page redirects to login with next", async ({ page }) => {
  await page.goto("/support");
  await page.waitForURL(/\/login\?next=%2Fsupport$/);
  await expect(page.getByLabel("Email")).toBeVisible();
});
