import { expect, test } from "@playwright/test";

import { readOtpCode } from "../helpers/mailpit";
import { closeDbPool, latestReportTokenForBorrower } from "../helpers/db";

// CQ-022 spec.md, H2: a signed-out visit to `/report/{token}` redirects to
// `/login?next=/report/{token}` (src/middleware.ts), and OTP success
// returns to that `next` path (AuthFlow.tsx). Needs `.env`'s
// SEED_BORROWER_PASSWORD and a seeded persona with a sent report.
const email = "luis.romero@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");
// Both tests below do a real login as the same persona and read Mailpit's
// *newest* OTP email for that address; `fullyParallel: true` would let
// them run concurrently across workers, racing on which login's OTP
// "newest" actually means at read time. Serial keeps them from ever
// overlapping.
test.describe.configure({ mode: "serial" });

test.afterAll(async () => {
  await closeDbPool();
});

test("a signed-out visit redirects to /login?next=..., and OTP success returns to the report", async ({
  page,
}) => {
  const token = await latestReportTokenForBorrower(email);

  // No prior login in this test -- Playwright gives each test a fresh
  // browser context, so there's no session cookie yet.
  await page.goto(`/report/${token}`);

  await expect(page).toHaveURL(`/login?next=${encodeURIComponent(`/report/${token}`)}`);
  await expect(page.getByRole("heading", { name: "Clear Quote" })).toBeVisible();

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByLabel("Verification code")).toBeVisible();
  const code = await readOtpCode(email);
  await page.getByLabel("Verification code").fill(code);
  await page.getByRole("button", { name: "Verify" }).click();

  await page.waitForURL(`/report/${token}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();
});

test("an unsafe next value never navigates off-site (open-redirect guard)", async ({ page }) => {
  // Middleware itself only ever builds `next` from the request's own
  // same-origin pathname (see src/middleware.ts), so this exercises the
  // client-side guard directly: a crafted `?next=` on the login page must
  // still resolve to a same-origin path after OTP success, not the raw
  // (attacker-controlled) value.
  await page.goto(`/login?next=${encodeURIComponent("//evil.example.com")}`);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByLabel("Verification code")).toBeVisible();
  const code = await readOtpCode(email);
  await page.getByLabel("Verification code").fill(code);
  await page.getByRole("button", { name: "Verify" }).click();

  await page.waitForURL("/");
  expect(page.url()).not.toContain("evil.example.com");
});
