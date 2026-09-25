import { expect, test } from "@playwright/test";

import { closeDbPool, latestReportTokenForBorrower } from "../helpers/db";
import { LUIS_ROMERO_STORAGE_STATE } from "../global-setup";

// CQ-022 spec.md AC3: needs `.env`'s SEED_BORROWER_PASSWORD and a seeded,
// non-expired, multi-option persona (`make demo-reset`). Luis Romero (STR,
// sent 3 days ago, Par + Buydown) fits -- Grace Kim is expired (AC4's own
// spec) and no other seeded persona has a `quote_package_versions` row.
// Signed in once by `e2e/global-setup.ts` (rate-limit friendly -- see its
// own comment); this file loads that saved session instead of a fresh
// `borrowerLogin` per test.
const email = "luis.romero@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");
test.use({ storageState: LUIS_ROMERO_STORAGE_STATE });

test.afterAll(async () => {
  await closeDbPool();
});

test("selecting Buydown updates hero numbers, sets ?option=, persists on reload, and shows the alternative-view note", async ({
  page,
}) => {
  const token = await latestReportTokenForBorrower(email);

  await page.goto(`/report/${token}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();

  const hero = page.locator('[data-testid="hero-numbers"]');
  const heroBefore = await hero.innerText();

  // No note yet -- the recommended (first/Par) option is selected by default.
  await expect(page.getByText(/viewing an alternative to our recommendation/i)).toHaveCount(0);

  await page.getByRole("radio", { name: /buydown/i }).click();

  await expect(page).toHaveURL(/\?option=/);
  const heroAfter = await hero.innerText();
  expect(heroAfter).not.toEqual(heroBefore);
  await expect(page.getByText(/viewing an alternative to our recommendation/i)).toBeVisible();

  // Reloading the exact URL keeps the Buydown selection (AC3).
  const urlAfterSelect = page.url();
  await page.reload();
  await expect(page).toHaveURL(urlAfterSelect);
  await expect(page.getByText(/viewing an alternative to our recommendation/i)).toBeVisible();
  const heroAfterReload = await hero.innerText();
  expect(heroAfterReload).toEqual(heroAfter);
});
