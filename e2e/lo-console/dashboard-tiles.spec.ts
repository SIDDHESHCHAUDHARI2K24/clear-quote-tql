import { expect, test } from "@playwright/test";

import { flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// CQ-025 spec.md. Needs `.env`'s SEED_STAFF_PASSWORD and `make
// demo-reset`'s seeded personas (seed/personas/*.yaml).
const password = process.env.SEED_STAFF_PASSWORD;
const ADMIN = "riley.admin@clearquote-demo.test";
const EVIDENCE = "docs/backlog/evidence/CQ-025-dashboard";

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

test("tiles are links with the spec.md query parameters", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);

  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();

  // Scoped to the tiles region -- the shell nav has its own "Clients" and
  // "Applications" links with the same accessible names.
  const tiles = page.getByRole("region", { name: "Dashboard tiles" });

  const expectedHrefs: Record<string, string> = {
    Clients: "/clients",
    Applications: "/applications",
    "Pre-approvals sent": "/applications?status=sent_or_later",
    "With a property": "/applications?has_property=true",
    "Awaiting your review": "/applications?status=Priced,Inquiry,OptionSelected",
    "Needs attention": "/applications?status=NeedsAttention",
    "Stale quotes": "/applications?status=Stale",
  };

  for (const [label, href] of Object.entries(expectedHrefs)) {
    const link = tiles.getByRole("link", { name: new RegExp(`${label}$`) });
    await expect(link).toHaveAttribute("href", href);
  }
  await page.screenshot({ path: `${EVIDENCE}/dashboard-tiles.png` });
});

test("each Applications-linked tile opens the list with exactly the tile's count (AC4, now that CQ-027 is merged)", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);

  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();

  // Scoped to the tiles region, same reason as the href test above. The
  // "Clients" tile links to `/clients` (still CQ-026's stub), not the
  // Applications list, so it's out of scope here -- spec.md "Out of
  // scope": "The list pages the tiles link to (CQ-026, CQ-027) beyond
  // agreeing the query parameters."
  const tiles = page.getByRole("region", { name: "Dashboard tiles" });
  const applicationsLinkedTileLabels = [
    "Applications",
    "Pre-approvals sent",
    "With a property",
    "Awaiting your review",
    "Needs attention",
    "Stale quotes",
  ];

  for (const label of applicationsLinkedTileLabels) {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();

    const link = tiles.getByRole("link", { name: new RegExp(`${label}$`) });
    const tileText = (await link.textContent()) ?? "";
    const expectedCount = Number(tileText.trim().match(/^\d+/)?.[0]);
    expect(Number.isFinite(expectedCount)).toBe(true);

    await link.click();
    await expect(page.getByRole("heading", { level: 1, name: "Applications" })).toBeVisible();

    // `Pagination`'s summary text ("Showing 1-25 of 42" or "No results")
    // carries the list's `total` -- the one number this AC needs, without
    // depending on page size or the table's rendered row count.
    const summary = page.getByText(/^(Showing .* of \d+|No results)$/);
    await expect(summary).toBeVisible();
    const summaryText = (await summary.textContent()) ?? "";
    const actualTotal =
      summaryText === "No results" ? 0 : Number(summaryText.match(/of (\d+)/)?.[1]);

    expect(actualTotal).toBe(expectedCount);
  }
});

test("Aisha, Luis and Grace show up in the right lists with their reasons (AC3)", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);

  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();

  const attention = page
    .getByRole("heading", { level: 3, name: "Needs your attention" })
    .locator("xpath=ancestor::section");
  await expect(attention.getByText("Aisha Coleman")).toBeVisible();
  await expect(attention.getByText("Cannot price: missing Occupancy")).toBeVisible();
  await expect(attention.getByText("Luis Romero")).toBeVisible();

  const stale = page
    .getByRole("heading", { level: 3, name: "Going stale" })
    .locator("xpath=ancestor::section");
  await expect(stale.getByText("Grace Kim")).toBeVisible();
});

// AC5 ("resolving Aisha's flag removes her from the attention list") used
// to be covered here with a direct DB mutation, as a stand-in for CQ-028's
// real re-verify endpoint before CQ-028 existed. CQ-028 has since merged,
// so that workaround is stale -- and because `test.describe.configure({
// mode: "serial" })` only serializes within this file, the direct DB
// mutation used to leak into `workspace.spec.ts`'s later Aisha Coleman
// test in the same full-suite run (both files share the seeded Aisha
// Coleman persona). AC5 is now covered end-to-end, through the real UI
// and pipeline, by `e2e/lo-console/aisha-occupancy-resume.spec.ts`'s
// "AC1: setting Aisha's occupancy resumes the pipeline to Priced and
// clears her from the dashboard" (see its own comment for the CQ-025/
// CQ-028 cross-reference).
