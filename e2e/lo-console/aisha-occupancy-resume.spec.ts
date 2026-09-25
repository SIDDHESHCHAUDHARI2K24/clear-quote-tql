import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// CQ-028 spec.md AC1: "Aisha Coleman: setting occupancy clears her flag, the
// workflow resumes, and within one pipeline run she reaches Priced with
// quotes." Occupancy lives on the Property tab (plan.md decision #28:
// `fields.py` resolves `occupancy_type`/`investment_strategy` to
// `ApplicationTab.PROPERTY`, and `service.py`'s `_property()` is the only
// tab builder that returns a `kind="loan"` record for them).
//
// Also covers CQ-025 spec.md AC5 (append-only note in
// docs/backlog/CQ-025-dashboard/post-dev.md): once her flag clears, Aisha
// leaves the dashboard's "Needs your attention" list within one refresh.
//
// Needs `.env`'s SEED_STAFF_PASSWORD, `make demo-reset`'s seeded Aisha
// Coleman (`missing_fields: [occupancy_type]`, `needs_attention`), and a
// running API + `make worker` on this worktree's slot (the resume signal
// starts/resumes the real Temporal pipeline -- see docs/backlog/CQ-028-
// verification-tabs/post-dev.md's own E2E section for the timing this spec
// mirrors: `needs_attention` -> `PUT occupancy_type` -> `priced`, 3 quotes).
const password = process.env.SEED_STAFF_PASSWORD;
const AISHAS_LO = "jordan.lee@clearquote-demo.test";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

test("AC1: setting Aisha's occupancy resumes the pipeline to Priced and clears her from the dashboard", async ({
  page,
}) => {
  // The full pipeline chain (see the 60s wait below) can outlast
  // Playwright's default 30s test timeout in a dev environment.
  test.setTimeout(120000);

  const applicationId = applicationIdByClientEmail("aisha.coleman@clearquote-demo.test");
  await staffLogin(page, AISHAS_LO, password!);

  await page.goto(`/applications/${applicationId}/property`);
  await expect(page.getByRole("heading", { name: "Property" })).toBeVisible();
  await expect(page.getByText("Occupancy", { exact: true })).toBeVisible();

  const loanCard = page.locator("section", { has: page.getByRole("heading", { name: "Loan" }) });
  await loanCard.getByRole("button", { name: "Edit" }).first().click();
  await page.getByLabel("Occupancy").selectOption("investment");
  await page.getByRole("button", { name: "Save" }).click();

  // spec.md "Shared pieces": the toast fires once the last blocking flag
  // clears and a resume is requested.
  await expect(
    page.getByRole("status").filter({ hasText: "All checks pass — pricing resumed" }),
  ).toBeVisible({ timeout: 10000 });

  // WorkspaceProvider polls `.../summary` every 3s while the pipeline is
  // running (CQ-016); the header's StatusPill updates on its own. The full
  // chain (verify -> enrich x3 -> auto-price -> draft quotes) is several
  // real Temporal activities against a dev-mode worker, so this gives it
  // real room rather than the UI's own much faster edit round trip.
  await expect(page.getByText("Priced", { exact: true })).toBeVisible({ timeout: 60000 });

  // CQ-025 AC5: she leaves "Needs your attention" within one refresh.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  const attention = page.locator("section", {
    has: page.getByRole("heading", { name: "Needs your attention" }),
  });
  await expect(attention.getByText("Aisha Coleman")).toHaveCount(0);
});
