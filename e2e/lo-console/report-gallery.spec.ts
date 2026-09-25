import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// CQ-021 AC6, LO Console side. `/gallery/report` is a public path
// (apps/lo-console/src/middleware.ts) -- same components, same fixtures,
// same ReportPage composition as the borrower-portal spec
// (e2e/borrower-portal/report-gallery.spec.ts), which also covers AC2-AC4
// in more depth; this spec's job is proving the LO Console's own render of
// the identical `@cq/ui` components is equally clean.

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

test("no critical or serious accessibility violations on the gallery page", async ({ page }) => {
  await page.goto("/gallery/report");

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
});
