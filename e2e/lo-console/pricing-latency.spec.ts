import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// AC7: "The p95 time from last keystroke to updated breakdown is under
// 600ms locally (250ms debounce + < 300ms preview + render)." Measures
// wall-clock time from the last keystroke in the purchase price field to
// the P&I figure actually changing on screen, over 10 edits, against a
// real running stack.
const staffPassword = process.env.SEED_STAFF_PASSWORD;
test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

const JORDAN_EMAIL = "jordan.lee@clearquote-demo.test";

test.beforeEach(() => {
  flushLoginRateLimit();
});

test("AC7: p95 keystroke-to-updated-breakdown latency is under 600ms", async ({ page }) => {
  const applicationId = applicationIdByClientEmail("priya.nair@clearquote-demo.test");
  await staffLogin(page, JORDAN_EMAIL, staffPassword!);
  await page.goto(`/applications/${applicationId}/pricing`);
  await expect(page.getByLabel("Loan amount")).toBeVisible();

  const priceInput = page.getByLabel("Purchase price");
  const piLocator = page.locator("text=P&I").locator("xpath=following-sibling::span[1]");

  // One untimed warm-up edit: the very first `/quotes/preview` round trip
  // in a fresh page can be slower than steady state (first-request
  // overhead unrelated to the debounce/preview path itself), which would
  // otherwise pollute the very first timed sample.
  {
    const beforeText = await piLocator.textContent();
    await priceInput.fill("330000");
    await expect
      .poll(async () => (await piLocator.textContent()) !== beforeText, { timeout: 5000 })
      .toBe(true);
  }

  const samples: number[] = [];
  let price = 330000;
  for (let i = 0; i < 10; i++) {
    price += 1000;
    const beforeText = await piLocator.textContent();
    const started = Date.now();
    await priceInput.fill(String(price));
    await expect
      .poll(async () => (await piLocator.textContent()) !== beforeText, { timeout: 2000 })
      .toBe(true);
    samples.push(Date.now() - started);
  }

  samples.sort((a, b) => a - b);
  const p95 = samples[Math.floor(samples.length * 0.95) - 1] ?? samples[samples.length - 1];
  // eslint-disable-next-line no-console
  console.log("pricing-latency samples (ms):", samples, "p95:", p95);
  expect(p95).toBeLessThan(600);
});
