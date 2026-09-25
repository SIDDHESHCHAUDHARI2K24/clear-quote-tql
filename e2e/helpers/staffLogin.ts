import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

import { readOtpCode } from "./mailpit";

// Drives the LO Console's staff login flow end to end: fills the
// email/password `CredentialsForm` (packages/ui/src/auth/CredentialsForm.tsx,
// composed by apps/lo-console/src/features/auth/LoginForm.tsx), waits for
// the OTP email in Mailpit, then completes the `OtpForm` step
// (apps/lo-console/src/features/auth/OtpForm.tsx). Leaves the browser on
// whatever page `AuthFlow`'s `onSuccess` navigates to ("/").
//
// `email`/`password` must be a seeded staff user (e.g.
// `jordan.lee@clearquote-demo.test` with `.env`'s `SEED_STAFF_PASSWORD` --
// see seed/users.yaml).
export async function staffLogin(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByLabel("Verification code")).toBeVisible();
  const code = await readOtpCode(email);
  await page.getByLabel("Verification code").fill(code);
  await page.getByRole("button", { name: "Verify" }).click();

  // `AuthFlow.onSuccess` does `router.replace("/")` on a verified OTP.
  await page.waitForURL("/");
}
