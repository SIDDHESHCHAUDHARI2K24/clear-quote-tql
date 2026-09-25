import { expect, test } from "@playwright/test";

import { closeDbPool, latestReportTokenForBorrower } from "../helpers/db";
import { LUIS_ROMERO_STORAGE_STATE } from "../global-setup";

// CQ-022 spec.md AC7: needs `.env`'s SEED_BORROWER_PASSWORD and a seeded,
// non-expired persona (Luis Romero, investment/STR -- 4 hero tiles, so the
// "2x2" stacked layout is meaningfully testable; a primary persona's 3
// tiles would only ever be "1x3", which is also the mobile default). Signed
// in once by `e2e/global-setup.ts`; loads that saved session here.
const email = "luis.romero@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");

test.use({ viewport: { width: 375, height: 800 }, storageState: LUIS_ROMERO_STORAGE_STATE });

test.afterAll(async () => {
  await closeDbPool();
});

test("no horizontal scroll and the 4 investment hero tiles stack 2x2 at 375px", async ({
  page,
}) => {
  const token = await latestReportTokenForBorrower(email);

  await page.goto(`/report/${token}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();

  const [scrollWidth, clientWidth] = await Promise.all([
    page.evaluate(() => document.documentElement.scrollWidth),
    page.evaluate(() => document.documentElement.clientWidth),
  ]);
  // Allow a 1px rounding slop; anything beyond that is real horizontal
  // overflow at the viewport width the AC pins.
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);

  const heroTiles = page.locator('[data-testid="hero-numbers"] > div');
  await expect(heroTiles).toHaveCount(4);

  const boxes = await Promise.all([0, 1, 2, 3].map((i) => heroTiles.nth(i).boundingBox()));
  expect(boxes.every((b) => b !== null)).toBe(true);
  const [tile0, tile1, tile2, tile3] = boxes as NonNullable<(typeof boxes)[number]>[];

  // 2x2: tiles 0/1 share a row, tiles 2/3 share a (lower) row.
  expect(Math.abs(tile0.y - tile1.y)).toBeLessThan(5);
  expect(Math.abs(tile2.y - tile3.y)).toBeLessThan(5);
  expect(tile2.y).toBeGreaterThan(tile0.y + tile0.height / 2);
});
