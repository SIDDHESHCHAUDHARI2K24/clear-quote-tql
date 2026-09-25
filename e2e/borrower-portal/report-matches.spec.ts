import { expect, test } from "@playwright/test";

import { closeDbPool, latestReportTokenForBorrower } from "../helpers/db";
import { KATHLEEN_MCREYNOLDS_STORAGE_STATE } from "../global-setup";

// CQ-023 spec.md AC1/AC8: needs `.env`'s SEED_BORROWER_PASSWORD, a seeded
// stack (`make demo-reset`), and a real sent version for Kathleen McReynolds
// -- the one TBD persona (buy-box FL/[Davenport, Orlando]) -- which
// `make demo-reset` alone doesn't create (she has no `fixture_layer` in her
// seed YAML, unlike Grace Kim/Luis Romero). `e2e/global-setup.ts` now runs
// `uv run python backend/scripts/freeze_version.py --persona
// kathleen_mcreynolds` automatically (idempotent -- reuses her existing
// version if one hasn't expired) before it signs her in, so no manual step
// is needed. Signed in once by `e2e/global-setup.ts` (rate-limit friendly --
// see its own comment); this file loads that saved session instead of a
// fresh `borrowerLogin` per test.
const email = "kathleen.mcreynolds@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(
  !password,
  "SEED_BORROWER_PASSWORD not set -- run make demo-reset, freeze_version.py --persona " +
    "kathleen_mcreynolds, and export SEED_BORROWER_PASSWORD first",
);
test.use({ storageState: KATHLEEN_MCREYNOLDS_STORAGE_STATE });

test.afterAll(async () => {
  await closeDbPool();
});

test("shows exactly 3 property matches with the section title and subtitle (AC1)", async ({
  page,
}) => {
  const token = await latestReportTokenForBorrower(email);

  await page.goto(`/report/${token}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();

  await expect(page.getByRole("heading", { name: "Your top 3 property matches" })).toBeVisible();
  await expect(
    page.getByText("Selected for your budget and markets, each run through the same numbers"),
  ).toBeVisible();
  await expect(page.getByTestId("match-card")).toHaveCount(3);
});

test("one column at 375px, three columns at 1120px (AC8)", async ({ page }) => {
  const token = await latestReportTokenForBorrower(email);

  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto(`/report/${token}`);

  const mobileCards = page.getByTestId("match-card");
  await expect(mobileCards).toHaveCount(3);
  const [scrollWidth, clientWidth] = await Promise.all([
    page.evaluate(() => document.documentElement.scrollWidth),
    page.evaluate(() => document.documentElement.clientWidth),
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);

  const mobileBox0 = await mobileCards.nth(0).boundingBox();
  const mobileBox1 = await mobileCards.nth(1).boundingBox();
  expect(mobileBox0).not.toBeNull();
  expect(mobileBox1).not.toBeNull();
  // Stacked: the second card sits below the first, not beside it.
  expect(mobileBox1!.y).toBeGreaterThan(mobileBox0!.y + mobileBox0!.height / 2);

  await page.setViewportSize({ width: 1120, height: 900 });
  await page.reload();

  const desktopCards = page.getByTestId("match-card");
  await expect(desktopCards).toHaveCount(3);
  const boxes = await Promise.all([0, 1, 2].map((i) => desktopCards.nth(i).boundingBox()));
  expect(boxes.every((b) => b !== null)).toBe(true);
  const [box0, box1, box2] = boxes as NonNullable<(typeof boxes)[number]>[];
  // Three columns: all three cards share (approximately) the same row.
  expect(Math.abs(box0.y - box1.y)).toBeLessThan(5);
  expect(Math.abs(box1.y - box2.y)).toBeLessThan(5);
});
