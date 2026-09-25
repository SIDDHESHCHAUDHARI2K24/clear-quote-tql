import { expect, test } from "@playwright/test";

import { closeDbPool, latestReportTokenForBorrower } from "../helpers/db";
import { GRACE_KIM_STORAGE_STATE } from "../global-setup";

// CQ-022 spec.md AC4: Grace Kim's seeded persona is sent 25 days ago
// (`seed/personas/p09_grace_kim.yaml`'s `fixture_layer.sent_days_ago: 25`),
// past the 21-day expiry (H2) -- needs `.env`'s SEED_BORROWER_PASSWORD and
// `make demo-reset`. Signed in once by `e2e/global-setup.ts`; loads that
// saved session here.
const email = "grace.kim@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");
test.use({ storageState: GRACE_KIM_STORAGE_STATE });

test.afterAll(async () => {
  await closeDbPool();
});

test("Grace Kim's report shows the expired banner and hides the action buttons", async ({
  page,
}) => {
  const token = await latestReportTokenForBorrower(email);

  await page.goto(`/report/${token}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();

  await expect(page.getByText("These numbers have expired.")).toBeVisible();
  await expect(page.getByTestId("actions-slot")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /move forward with this option/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /ask about another option/i })).toHaveCount(0);
});
