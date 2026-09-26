import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, execSql, flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// CQ-028 spec.md AC6: "Picking FL then Tampa and Orlando in the buy-box
// stores both metros; switching Kathleen's property from TBD to an address
// turns recommend-matches off and removes the TBD label" (plan.md decision
// #30: the TBD label lives on the Property tab itself, not CQ-016's global
// sticky header -- see `AddressOrTbdForm`'s `property-tbd-label` testid).
// Needs `.env`'s SEED_STAFF_PASSWORD, `make demo-reset`'s seeded personas
// (Kathleen McReynolds is `property_address_status: TBD`; her seed row
// already has buy-box FL/[Davenport, Orlando] -- seed/personas/
// p02_kathleen_mcreynolds.yaml, also used by CQ-023's report-matches.spec.ts
// -- so this test swaps Davenport for Tampa to land on "FL, [Tampa,
// Orlando]" per the AC's own wording rather than assuming an empty
// buy-box), and the API + worker running on this worktree's slot.
//
// Every buy-box checkbox is React-controlled and round-trips through a real
// `PATCH /property` before its `checked` attribute updates, so this uses
// `.click()` + a separately-retrying `expect(...).toBeChecked()` rather
// than Playwright's `.check()`/`.uncheck()` -- those verify the resulting
// state right after the click with too short a window for a real network
// round trip against a dev-mode API, and fail with "Clicking the checkbox
// did not change its state" even though the click (and the PATCH it
// triggers) succeeded a moment later.
const password = process.env.SEED_STAFF_PASSWORD;
const KATHLEENS_LO = "morgan.reyes@clearquote-demo.test";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

// P56-merge: restore Kathleen's seeded property (TBD, buy-box FL/[Davenport,
// Orlando], recommend matches on). Main's CQ-019 `send-tab-draft.spec.ts`
// AC3 previews her letter with "- TBD -" and runs after this file in a
// full-suite run. City/state/zip/county are the seeded values already.
test.afterAll(() => {
  const applicationId = applicationIdByClientEmail("kathleen.mcreynolds@clearquote-demo.test");
  execSql(
    `update properties set address_status = 'tbd', street_address = null, ` +
      `buy_box_states = '{FL}', buy_box_metros = '{Davenport,Orlando}', ` +
      `recommend_matches = true where application_id = '${applicationId}';`,
  );
});

test("AC6: buy-box states -> metros, then TBD -> address turns recommend matches off and removes the TBD label", async ({
  page,
}) => {
  const applicationId = applicationIdByClientEmail("kathleen.mcreynolds@clearquote-demo.test");
  await staffLogin(page, KATHLEENS_LO, password!);

  await page.goto(`/applications/${applicationId}/property`);
  await expect(page.getByRole("heading", { name: "Property" })).toBeVisible();

  // Starts TBD (seed/personas/p02_kathleen_mcreynolds.yaml:
  // property_address_status TBD), with recommend-matches on by default for
  // a TBD property.
  const tbdLabel = page.getByTestId("property-tbd-label");
  await expect(tbdLabel).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Recommend matches" })).toBeChecked();

  // Scoped to the "Property" card -- the shell's own `UserMenu`
  // (apps/lo-console/src/features/shell/UserMenu.tsx) also renders a
  // `button[aria-expanded]` on every page, ahead of this one in the DOM.
  const propertyCard = page.locator("section", {
    has: page.getByRole("heading", { name: "Property", exact: true }),
  });
  const multiSelectTriggers = () => propertyCard.locator("button[aria-expanded]");

  // "Picking FL" -- already selected from the seed, so just confirm it.
  await expect(multiSelectTriggers().nth(0)).toHaveText(/Florida/);

  // "...then Tampa and Orlando": Orlando is already selected; swap Davenport
  // for Tampa so the end state is exactly [Tampa, Orlando].
  await expect(multiSelectTriggers().nth(1)).toBeEnabled();
  await multiSelectTriggers().nth(1).click();

  await propertyCard.getByRole("checkbox", { name: "Davenport (FL)" }).click();
  await expect(propertyCard.getByRole("checkbox", { name: "Davenport (FL)" })).not.toBeChecked();

  await propertyCard.getByRole("checkbox", { name: "Tampa (FL)" }).click();
  await expect(propertyCard.getByRole("checkbox", { name: "Tampa (FL)" })).toBeChecked();
  await expect(propertyCard.getByRole("checkbox", { name: "Orlando (FL)" })).toBeChecked();
  await expect(multiSelectTriggers().nth(1)).toHaveText(/2 selected/);

  // TBD -> a specific address.
  await page.getByRole("button", { name: "Enter address" }).click();
  await page.getByLabel("Street address").fill("100 Lake Dr");
  await page.getByLabel("City").fill("Davenport");
  await page.getByLabel("State", { exact: true }).selectOption("FL");
  await page.getByLabel("Zip").fill("33896");
  await page.getByRole("button", { name: "Save address" }).click();

  await expect(tbdLabel).not.toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Recommend matches" })).not.toBeChecked();
  // County filled from the zip via the mock lookup (plan.md #16).
  await expect(page.getByText("Polk")).toBeVisible();
});
