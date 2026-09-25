import { expect, test } from "@playwright/test";
// pdf-parse ships as CJS; default import works under Playwright's TS/esbuild
// transform (same as its own use elsewhere in the Node ecosystem).
import pdfParse from "pdf-parse";

import { closeDbPool, latestReportTokenForBorrower } from "../helpers/db";
import { LUIS_ROMERO_STORAGE_STATE } from "../global-setup";

// CQ-022 spec.md AC6: needs `.env`'s SEED_BORROWER_PASSWORD and a seeded,
// non-expired, multi-option persona (Luis Romero -- see
// report-option-switch.spec.ts's own note). `page.pdf()` only works in
// headless Chromium (Playwright's documented limitation), which is this
// project's default `pnpm exec playwright test` mode. Signed in once by
// `e2e/global-setup.ts`; loads that saved session here.
const email = "luis.romero@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");
test.use({ storageState: LUIS_ROMERO_STORAGE_STATE });

test.afterAll(async () => {
  await closeDbPool();
});

test("print preview contains the hero numbers and both expanded sections, with no switcher or action buttons", async ({
  page,
}) => {
  const token = await latestReportTokenForBorrower(email);

  await page.goto(`/report/${token}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();
  // Both collapsibles are closed on screen by default; print CSS forces
  // them open regardless (Collapsible.tsx: content always mounts, a plain
  // `.hidden` class drives the closed state on screen, `print:block`
  // overrides it under print media) -- no click-to-expand needed before
  // calling page.pdf().

  const pdfBuffer = await page.pdf();
  const { text, numpages } = await pdfParse(pdfBuffer);

  // Hero numbers (system-design.md "Hero numbers"; Luis is investment/STR,
  // so 4 tiles).
  expect(text).toMatch(/Total monthly payment/i);
  expect(text).toMatch(/Cash to close/i);
  expect(text).toMatch(/Estimated monthly cashflow/i);
  expect(text).toMatch(/Estimated year-1 tax savings/i);

  // "See the full breakdown" section's own content (BreakdownTable +
  // CashflowTable headings) -- present without ever clicking to expand.
  expect(text).toMatch(/Monthly payment/i);
  expect(text).toMatch(/Cash to close/i);
  expect(text).toMatch(/Qualifying rent/i);
  expect(text).toMatch(/DSCR/i);

  // "See all N options we priced" section's own content (ComparisonTable).
  // Its narrow header column wraps "Prepayment penalty" onto two lines, so
  // pdf-parse extracts a newline (not a space) between the words.
  expect(text).toMatch(/Prepayment\s+penalty/i);

  // No switcher/action-button chrome (Collapsible toggle buttons, the
  // OptionSwitcher pills' container, and ReportActionsSlot are all
  // `print:hidden`).
  expect(text).not.toMatch(/Coming soon/i);
  expect(text).not.toMatch(/Save as PDF/i);
  expect(text).not.toMatch(/See the full breakdown/i);
  expect(text).not.toMatch(/See all \d+ options we priced/i);

  // Sanity bound on page count -- not a precise page-break assertion
  // (pdf-parse's flat text extraction can't see layout geometry; the real
  // mechanism is each table block's `print:break-inside-avoid` CSS,
  // verified by the print CSS itself, not by this count).
  expect(numpages).toBeGreaterThan(0);
  expect(numpages).toBeLessThanOrEqual(4);
});
