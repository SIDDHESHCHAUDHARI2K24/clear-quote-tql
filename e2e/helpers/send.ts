import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

// CQ-020: opens an application's Send tab ready to send. Earlier specs in
// the same run (CQ-017 `pricing-panel.spec.ts` AC3 overrides Marcus Hale's
// property tax) can leave his quotes stale, which blocks sending ("Quotes
// are out of date"). This re-prices them the way an LO would -- the
// Pricing tab's "Re-price" button (CQ-018 AC8) -- then comes back.
export async function openSendTabReady(page: Page, applicationId: string): Promise<void> {
  const sendPath = `/applications/${applicationId}/send`;
  await page.goto(sendPath);
  const ready = page.getByText("Ready to send");
  const stale = page.getByTestId("readiness-blockers").getByText("Quotes are out of date");
  await expect(ready.or(stale)).toBeVisible({ timeout: 15_000 });
  if (await ready.isVisible()) return;

  await page.goto(`/applications/${applicationId}/pricing`);
  await page.getByRole("button", { name: "Re-price" }).click();
  await expect(page.getByText("Quotes are out of date — Re-price")).toBeHidden({
    timeout: 15_000,
  });
  await page.goto(sendPath);
  await expect(ready).toBeVisible({ timeout: 15_000 });
}
