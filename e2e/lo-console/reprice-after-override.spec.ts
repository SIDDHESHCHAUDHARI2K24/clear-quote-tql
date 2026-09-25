import path from "node:path";

import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// CQ-018 AC8: after a CQ-017 override marks quotes stale, "Re-price" clears
// the stale banner and moves `priced_at` forward on every quote.
const staffPassword = process.env.SEED_STAFF_PASSWORD;
test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

const MANAGER_EMAIL = "casey.nguyen@clearquote-demo.test";
const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-018-quote-builder/evidence");

test.beforeEach(() => {
  flushLoginRateLimit();
});

test("AC8: Re-price after an override clears the banner and updates priced_at on every quote", async ({
  page,
}) => {
  // Tom & Lisa Brandt: untouched by every other spec in this suite.
  const applicationId = applicationIdByClientEmail("tom.brandt@clearquote-demo.test");
  await staffLogin(page, MANAGER_EMAIL, staffPassword!);
  await page.goto(`/applications/${applicationId}/pricing`);
  const builder = page.getByRole("region", { name: "Quote builder" });
  const cards = builder.getByRole("article");
  await expect(cards.first()).toBeVisible();
  const before = await cards.evaluateAll((els) =>
    els.map((el) => el.getAttribute("data-priced-at") ?? ""),
  );
  expect(before.length).toBeGreaterThan(0);

  const taxInput = page.getByLabel("Property tax annual rate");
  await taxInput.fill("1.500");
  await taxInput.blur();

  const banner = page.getByText("Quotes are out of date — Re-price");
  await expect(banner).toBeVisible();
  await expect(builder.locator('[data-stale="true"]')).toHaveCount(before.length);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "ac8-stale-banner.png") });

  await page.getByRole("button", { name: "Re-price" }).click();
  await expect(banner).toBeHidden({ timeout: 15000 });
  await expect(builder.locator('[data-stale="true"]')).toHaveCount(0);

  const after = await cards.evaluateAll((els) =>
    els.map((el) => el.getAttribute("data-priced-at") ?? ""),
  );
  expect(after).toHaveLength(before.length);
  for (let i = 0; i < after.length; i += 1) {
    expect(Date.parse(after[i])).toBeGreaterThan(Date.parse(before[i]));
  }
  await builder.screenshot({ path: path.join(EVIDENCE_DIR, "ac8-after-reprice.png") });
});
