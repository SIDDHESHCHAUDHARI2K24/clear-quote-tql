import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, execSql, flushLoginRateLimit } from "../helpers/db";
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

// This test permanently resolves Aisha's blocking flag and prices her
// application for real (the whole point of AC1) -- but several other
// specs in a full-suite run (`dashboard-tiles.spec.ts`'s AC3,
// `workspace.spec.ts`'s AC4, `applications-list.spec.ts`'s status-filter
// test, `portal-home.spec.ts`'s AC1/AC2) still assert her *original*
// seeded state (`needs_attention`, missing occupancy, the "Cannot price:
// missing Occupancy" flag). This file runs first alphabetically in
// `e2e/lo-console`, ahead of all of those, so without this `afterAll` her
// resumed-to-Priced state would leak into every one of them. Restores
// exactly the columns those specs read: `write_flag`/`resolve_flag`
// (verification/service.py) only ever set `resolved_at` on the existing
// row, never delete it, so re-opening it (not fabricating a new one)
// reproduces the original unresolved "missing Occupancy" flag exactly.
// Scoped to the exact `(field_key, rule)` the OB-required-field validator
// uses for occupancy (`enrichment/service.py`'s `_flag_field_key("Occupancy")`
// == `"occupancy_type"`, `_OB_REQUIRED_FLAG_RULE` == `"ob_required_field"`)
// rather than every resolved flag on the application: `validate_ob_
// required_fields` calls `resolve_flag` for every field in `ALWAYS_
// REQUIRED` on each successful run, so if the real pipeline this test
// triggers ever raises-then-resolves a flag for some other field along
// the way, a blanket "any resolved flag" restore would incorrectly reopen
// that one too.
// Leftover `scenarios`/`quotes`/`activity_events` rows from the real
// pipeline run stay in place -- nothing else in the suite asserts their
// absence for Aisha.
//
// `updated_at` also needs resetting by hand: it's an ORM-level
// `onupdate=func.now()` (applications/models.py), not a DB trigger, so
// this raw SQL restore doesn't touch it, and it's left at the real
// pipeline's (very recent) timestamp. `dashboard/service.py`'s
// `_build_attention` sorts the attention list `updated_at.asc()` with a
// `limit(10)` -- her *originally* seeded `updated_at` is one of the
// earliest of any `needs_attention` row (personas seed before the 200
// background applications), so a stale recent timestamp would silently
// sort her out of that top-10 window and fail `dashboard-tiles.spec.ts`'s
// AC3. `'epoch'` guarantees she sorts first, same as (or earlier than)
// her real seeded position.
test.afterAll(() => {
  const applicationId = applicationIdByClientEmail("aisha.coleman@clearquote-demo.test");
  execSql(
    `update applications set status = 'needs_attention', occupancy = null, ` +
      `last_pipeline_stage = null, recommended_quote_id = null, updated_at = 'epoch' ` +
      `where id = '${applicationId}';`,
  );
  execSql(
    `update flags set resolved_at = null where application_id = '${applicationId}' ` +
      `and field_key = 'occupancy_type' and rule = 'ob_required_field' ` +
      `and resolved_at is not null;`,
  );
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
