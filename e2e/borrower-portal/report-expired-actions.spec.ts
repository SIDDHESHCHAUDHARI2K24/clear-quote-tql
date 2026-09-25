import path from "node:path";

import { expect, test } from "@playwright/test";

import { closeDbPool, latestReportTokenForBorrower } from "../helpers/db";
import { GRACE_KIM_STORAGE_STATE } from "../global-setup";

const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-024-borrower-actions/evidence");

// CQ-024 spec.md AC4: Grace Kim's seeded persona is sent 25 days ago
// (past the 21-day expiry, H2) -- her report shows only "Ask for updated
// numbers", which works, and move_forward 409s. Reuses the session
// `e2e/global-setup.ts` already signed in for `report-expired.spec.ts`
// (CQ-022), instead of a fresh login, to stay well under the borrower
// login rate limit across the whole suite.
const email = "grace.kim@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");
test.use({ storageState: GRACE_KIM_STORAGE_STATE });

test.afterAll(async () => {
  await closeDbPool();
});

test("expired report: only 'Ask for updated numbers' is shown, and it works", async ({ page }) => {
  const token = await latestReportTokenForBorrower(email);

  await page.goto(`/report/${token}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();
  await expect(page.getByText("These numbers have expired.")).toBeVisible();

  await expect(page.getByRole("button", { name: /move forward with this option/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^ask about another option/i })).toHaveCount(0);

  const askUpdated = page.getByRole("button", { name: /ask for updated numbers/i });
  await expect(askUpdated).toBeVisible();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "expired-ask-updated-button.png") });
  await askUpdated.click();

  await expect(page.getByText(/will follow up with updated numbers/i)).toBeVisible();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "expired-ask-updated-sent.png") });
});
