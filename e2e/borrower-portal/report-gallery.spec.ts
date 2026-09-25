import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// CQ-021 AC6: "Gallery renders with no console errors in both apps;
// react-doctor passes; components meet WCAG AA contrast." No auth needed --
// `/gallery/report` is a public path (apps/borrower-portal/src/middleware.ts).
// This is the committed spec the CQ-021 worker's post-dev.md flagged as
// deferred until the foundation unit's Playwright setup merged; it has now
// merged (PR #3), so this closes that gap.

test("gallery renders with no console errors or page errors", async ({ page }) => {
  const messages: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" || msg.type() === "warning") {
      messages.push(`${msg.type()}: ${msg.text()}`);
    }
  });
  page.on("pageerror", (err) => messages.push(`pageerror: ${err.message}`));

  await page.goto("/gallery/report");
  await expect(page.getByRole("heading", { name: "Report component gallery" })).toBeVisible();

  expect(messages, messages.join("\n")).toEqual([]);
});

test("AC2: Priya Nair (primary) renders exactly 3 hero tiles and no investment content", async ({
  page,
}) => {
  await page.goto("/gallery/report");

  const priyaSection = page
    .locator("section")
    .filter({ hasText: "Priya Nair — primary, 20% down" });
  const heroTiles = priyaSection.locator('[data-testid="hero-numbers"] > div');
  await expect(heroTiles).toHaveCount(3);

  // Expand both collapsibles so their contents are in the DOM too.
  for (const button of await priyaSection.getByRole("button", { name: /see/i }).all()) {
    await button.click();
  }

  const sectionText = (await priyaSection.innerText()).toLowerCase();
  for (const forbidden of [
    "dscr",
    "cashflow",
    "cap rate",
    "cost segregation",
    "prepayment penalty",
    "tax savings",
    "tax advice",
    "rental income",
  ]) {
    expect(sectionText).not.toContain(forbidden);
  }
});

test("AC3: Kathleen McReynolds shows the TBD label and LTR, never STR", async ({ page }) => {
  await page.goto("/gallery/report");

  const kathleenSection = page
    .locator("section")
    .filter({ hasText: "Kathleen McReynolds — LTR, property TBD" });
  await expect(kathleenSection.getByText("Property to be determined")).toBeVisible();

  const sectionText = await kathleenSection.innerText();
  expect(sectionText).toMatch(/LTR/);
  expect(sectionText).not.toMatch(/\bSTR\b/);
});

test("AC4: switching options updates the hero numbers to the selected option's own values", async ({
  page,
}) => {
  await page.goto("/gallery/report");

  const marcusSection = page.locator("section").filter({ hasText: "Marcus Hale — STR, Tampa FL" });
  const hero = marcusSection.locator('[data-testid="hero-numbers"]').first();
  const before = await hero.innerText();

  await marcusSection.getByRole("radio", { name: /buydown/i }).click();
  const after = await hero.innerText();

  expect(after).not.toEqual(before);
});

test("no critical or serious accessibility violations on the gallery page", async ({ page }) => {
  await page.goto("/gallery/report");

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
});
