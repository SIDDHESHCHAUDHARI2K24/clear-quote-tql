import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

import { readOtpCode } from "./mailpit";

// Drives the Borrower Portal's login flow end to end: same shape as
// `staffLogin` (shared `CredentialsForm`/`OtpForm` from packages/ui), but
// against apps/borrower-portal/src/features/auth -- `/login` renders
// `AuthFlow mode="login"` (apps/borrower-portal/src/app/login/page.tsx).
//
// `next` (optional) mirrors CQ-022's `/login?next=/report/{token}` --
// after OTP verification `AuthFlow` still does `router.replace("/")`
// itself (CQ-022 wires `next` through separately), so this helper waits
// on `/` unless the caller passes an explicit `expectUrl`.
export async function borrowerLogin(
  page: Page,
  email: string,
  password: string,
  options: { next?: string; expectUrl?: string | RegExp } = {},
): Promise<void> {
  const loginPath = options.next ? `/login?next=${encodeURIComponent(options.next)}` : "/login";
  await page.goto(loginPath);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByLabel("Verification code")).toBeVisible();
  const code = await readOtpCode(email);
  await page.getByLabel("Verification code").fill(code);
  await page.getByRole("button", { name: "Verify" }).click();

  await page.waitForURL(options.expectUrl ?? "/");
}
