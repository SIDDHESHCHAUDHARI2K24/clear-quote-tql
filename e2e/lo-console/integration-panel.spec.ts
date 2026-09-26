import { expect, test } from "@playwright/test";

import { flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// spec.md CQ-029 "Integration panel" (Admin only). Needs `.env`'s
// SEED_STAFF_PASSWORD and `make demo-reset`'s seeded staff users
// (seed/users.yaml).
//
// AC4's full round trip (force PricingClient to fail -> re-price ->
// NeedsAttention with the named error -> toggle off -> re-price succeeds)
// is proven against the real Temporal workflow in
// `backend/app/workflows/tests/test_admin_forced_pricing_failure.py`, not
// here: every seeded persona's `application_parties`/housing/etc. rows
// were already written directly by `seed/loader.py::seed_persona` (not
// through the real `ApplicationPipelineWorkflow`), so a `POST .../
// pipeline/start` against a seeded persona runs `import_application` for
// the first time from Temporal's point of view and re-inserts those same
// rows, hitting an unrelated unique-constraint violation -- not the
// forced-failure path this AC is about. CQ-018 (not yet built) is what
// adds a real "reprice" UI action that skips import; until then, this
// spec covers what the live demo panel itself does: toggling the switch,
// the banner, and admin-only access (AC4's UI half, AC5).
const password = process.env.SEED_STAFF_PASSWORD;
const ADMIN = "riley.admin@clearquote-demo.test";
const LO = "jordan.lee@clearquote-demo.test";
const EVIDENCE = "docs/backlog/CQ-029-timeline-outbox-panel/evidence";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

test("AC5: a non-admin gets no menu entry and is refused the page", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, LO, password!);

  await page.getByRole("button", { name: /Jordan/ }).click();
  await expect(page.getByRole("link", { name: "Integrations" })).toHaveCount(0);

  await page.goto("/admin/integrations");
  await expect(page.getByRole("heading", { name: "Not authorized" })).toBeVisible();
});

test("AC4/AC5: admin forces PricingClient to fail, sees the banner, then turns it back off", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);
  await page.goto("/admin/integrations");

  await expect(page.getByRole("heading", { level: 1, name: "Integrations" })).toBeVisible();
  // AC5: every adapter, with its last call/latency/result after
  // `make demo-reset`'s pipeline runs.
  for (const adapter of [
    "credit",
    "crm",
    "insurance",
    "los",
    "pricing",
    "property_search",
    "rent",
    "str",
    "tax",
  ]) {
    await expect(page.getByText(adapter, { exact: true })).toBeVisible();
  }
  await expect(page.getByText("Optimal Blue")).toBeVisible();

  // Scoped by text, not just role -- Next.js's dev-mode route announcer is
  // also `role="alert"` (empty text, always present), so a bare
  // `getByRole("alert")` count would never reach 0.
  const forcedBanner = page.getByRole("alert").filter({ hasText: "forced to fail" });
  const pricingCheckbox = page.getByRole("checkbox", { name: "Force pricing to fail" });
  // Self-healing precondition: recover from a previous interrupted run
  // that left the real toggle (Valkey-backed, outlives this test) on.
  if (await pricingCheckbox.isChecked()) {
    await pricingCheckbox.uncheck();
  }
  await expect(pricingCheckbox).not.toBeChecked();
  await expect(forcedBanner).toHaveCount(0);

  await pricingCheckbox.check();
  await expect(pricingCheckbox).toBeChecked();
  await expect(forcedBanner).toContainText("forced to fail");
  await page.screenshot({ path: `${EVIDENCE}/admin-integrations-forced.png` });

  await pricingCheckbox.uncheck();
  await expect(pricingCheckbox).not.toBeChecked();
  await expect(forcedBanner).toHaveCount(0);
});

test("the admin can run the stale check now and see the returned counts", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);
  await page.goto("/admin/integrations");

  const runButton = page.getByRole("button", { name: "Run stale check now" });
  await expect(runButton).toBeVisible();
  await runButton.click();

  // CQ-030's `POST /admin/jobs/stale-check` returns the counts it
  // changed -- zero on a repeat run against freshly seeded data, or a
  // "Marked N quote(s) stale, ..." sentence otherwise. Either way the
  // button stops saying "Running…" and a result line appears.
  await expect(runButton).toHaveText("Run stale check now");
  await expect(page.getByText(/nothing was stale|marked \d+ quotes? stale/i)).toBeVisible();
  await page.screenshot({ path: `${EVIDENCE}/admin-integrations-stale-check.png` });
});

test("AC6: the settings page lists the pricing config, read-only", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);
  await page.goto("/admin/settings");

  await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  await expect(page.getByText("fee_lender_processing")).toBeVisible();
  await expect(page.getByText("stale_quote_days")).toBeVisible();
  await expect(page.getByText("Seed").first()).toBeVisible();
  await expect(page.getByText("Config default").first()).toBeVisible();
  // Read-only: no input/button that would edit a value.
  await expect(page.getByRole("button", { name: /save/i })).toHaveCount(0);
  await page.screenshot({ path: `${EVIDENCE}/admin-settings.png` });
});
