// CQ-019 Send tab: AC6 (draft edits persist after reload) plus the preview
// checks (AC1 default draft, AC3/AC4 letter, AC5 blockers, AC7 sandbox).
// AC6 edits Sam Reed's package (Jordan's persona); `afterAll` below PUTs
// his original draft back (M10, post-merge review), so a rerun of this
// file no longer needs `make demo-reset` first.
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { loConsoleApiBaseUrl } from "../helpers/env";
import { staffLogin } from "../helpers/staffLogin";

const staffPassword = process.env.SEED_STAFF_PASSWORD;
test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

const LO_EMAIL = "jordan.lee@clearquote-demo.test";
const MANAGER_EMAIL = "casey.nguyen@clearquote-demo.test";
const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-019-send-tab/evidence");

test.describe.configure({ mode: "serial" });

interface PackageBody {
  quote_ids: string[];
  recommended_quote_id: string | null;
  lo_note: string | null;
}

// M10 (post-merge review): the AC6 test below edits Sam Reed's real draft
// (removes a quote, changes the recommendation, sets a note) -- captured
// here before it does, and PUT back once every test in this file has run,
// so a rerun doesn't need `make demo-reset` first (the file header's old
// claim) and other specs sharing Sam Reed's persona see his seeded state.
let originalSamPackage: PackageBody | null = null;

async function packagePut(page: Page, applicationId: string, body: PackageBody): Promise<void> {
  const apiBaseUrl = loConsoleApiBaseUrl();
  await page.evaluate(
    async ({ apiBaseUrl, applicationId, body }) => {
      const response = await fetch(`${apiBaseUrl}/api/v1/applications/${applicationId}/package`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`PUT /package failed: ${response.status}`);
    },
    { apiBaseUrl, applicationId, body },
  );
}

async function packageGet(page: Page, applicationId: string): Promise<PackageBody> {
  const apiBaseUrl = loConsoleApiBaseUrl();
  return page.evaluate(
    async ({ apiBaseUrl, applicationId }) => {
      const response = await fetch(`${apiBaseUrl}/api/v1/applications/${applicationId}/package`, {
        credentials: "include",
      });
      const data = await response.json();
      return {
        quote_ids: data.quote_ids as string[],
        recommended_quote_id: data.recommended_quote_id as string | null,
        lo_note: data.lo_note as string | null,
      };
    },
    { apiBaseUrl, applicationId },
  );
}

test.afterAll(async ({ browser }) => {
  if (!originalSamPackage || !staffPassword) return;
  const applicationId = applicationIdByClientEmail("sam.reed@clearquote-demo.test");
  const context = await browser.newContext();
  const page = await context.newPage();
  await staffLogin(page, LO_EMAIL, staffPassword);
  await packagePut(page, applicationId, originalSamPackage);
  await context.close();
});

// A TBD persona's report runs CQ-023's property matches through the mock
// providers' simulated latency (several seconds), so previews get longer.
const PREVIEW = { timeout: 30_000 };

test.beforeEach(async ({ page }) => {
  flushLoginRateLimit();
  await page.setViewportSize({ width: 1440, height: 1400 });
});

async function openSend(page: Page, email: string, clientEmail: string) {
  const applicationId = applicationIdByClientEmail(clientEmail);
  await staffLogin(page, email, staffPassword!);
  await page.goto(`/applications/${applicationId}/send`);
  await expect(page.getByRole("group", { name: "Quotes to send" })).toBeVisible();
  return applicationId;
}

test("AC1 + AC7: Marcus Hale's default draft, report preview and sandboxed letter", async ({
  page,
}) => {
  await openSend(page, LO_EMAIL, "marcus.hale@clearquote-demo.test");
  const selected = page.getByTestId("selected-quote");
  await expect(selected).toHaveCount(3);
  await expect(selected.nth(0).getByRole("radio")).toBeChecked();
  await expect(page.getByTestId("recommendation-text")).toHaveText(
    /^\d+(\.\d+)?% down · (Par|Buydown|Manual) pricing at \d\.\d{3}%/,
  );
  await expect(page.getByTestId("report-preview")).toContainText("here are your numbers", PREVIEW);
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "ac1-marcus-send-tab.png"),
    fullPage: true,
  });

  await page.getByRole("tab", { name: "Pre-approval letter" }).click();
  const frame = page.getByTestId("letter-frame");
  await expect(frame).toBeVisible(PREVIEW);
  // AC7: the iframe carries `sandbox` with no allow-scripts.
  expect(await frame.getAttribute("sandbox")).toBe("");
  expect(
    await frame.evaluate((el) => (el as HTMLIFrameElement).sandbox.contains("allow-scripts")),
  ).toBe(false);
  await expect(
    page.frameLocator('[data-testid="letter-frame"]').getByTestId("letter-borrower"),
  ).toHaveText("Marcus Hale");
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "ac7-marcus-letter.png"), fullPage: true });
});

test("AC5: Grace Kim and Aisha Coleman are blocked; Send is disabled", async ({ page }) => {
  await openSend(page, LO_EMAIL, "grace.kim@clearquote-demo.test");
  const blockers = page.getByTestId("readiness-blockers");
  await expect(blockers).toContainText("Quotes are out of date");
  await expect(blockers.getByRole("link", { name: "Go to Pricing" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send to borrower" })).toBeDisabled();
  await expect(page.getByTestId("send-button-wrapper")).toHaveAttribute(
    "title",
    "Quotes are out of date",
  );
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "ac5-grace-blocked.png"), fullPage: true });

  const aisha = applicationIdByClientEmail("aisha.coleman@clearquote-demo.test");
  await page.goto(`/applications/${aisha}/send`);
  await expect(page.getByTestId("readiness-blockers")).toContainText(
    "Open flag: Occupancy type — required for pricing",
  );
  await expect(page.getByRole("button", { name: "Send to borrower" })).toBeDisabled();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "ac5-aisha-blocked.png"), fullPage: true });
});

test("AC3 + AC4: letter previews for Kathleen (TBD) and Sam Reed (LLC)", async ({ page }) => {
  await openSend(page, MANAGER_EMAIL, "kathleen.mcreynolds@clearquote-demo.test");
  await page.getByRole("tab", { name: "Pre-approval letter" }).click();
  const kathleen = page.frameLocator('[data-testid="letter-frame"]');
  await expect(kathleen.getByTestId("letter-property")).toHaveText("- TBD -", PREVIEW);
  await expect(kathleen.getByTestId("letter-fico")).toHaveText(
    /Credit score (\d{3}\+|\d{3}–\d{3})/,
  );
  await expect(kathleen.getByTestId("letter-assets")).toHaveText(/Verified Assets \$[\d,]+K\+/);
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "ac3-kathleen-letter.png"),
    fullPage: true,
  });

  const sam = applicationIdByClientEmail("sam.reed@clearquote-demo.test");
  await page.goto(`/applications/${sam}/send`);
  await page.getByRole("tab", { name: "Pre-approval letter" }).click();
  const letter = page.frameLocator('[data-testid="letter-frame"]');
  await expect(letter.getByTestId("letter-borrower")).toHaveText("Asheville Holdings LLC", PREVIEW);
  await expect(letter.getByTestId("letter-property")).toHaveText(
    /^212 Merrimon Ave, Asheville, NC/,
  );
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "ac4-sam-reed-letter.png"),
    fullPage: true,
  });
});

test("AC6: removing a quote, changing the recommendation and the note persist after reload", async ({
  page,
}) => {
  const applicationId = await openSend(page, LO_EMAIL, "sam.reed@clearquote-demo.test");
  originalSamPackage = await packageGet(page, applicationId);
  const selected = page.getByTestId("selected-quote");
  await expect(selected).toHaveCount(3);
  const saved = () =>
    page.waitForResponse(
      (r) => r.url().endsWith("/package") && r.request().method() === "PUT" && r.ok(),
    );

  // Remove the last quote.
  const removedName = await selected.nth(2).getByRole("checkbox").getAttribute("aria-label");
  await Promise.all([saved(), selected.nth(2).getByRole("checkbox").click()]);
  await expect(selected).toHaveCount(2);

  // Recommend the second quote.
  await Promise.all([saved(), selected.nth(1).getByRole("radio").click()]);
  await expect(page.getByTestId("save-status")).toHaveText("All changes saved");
  const recommendation = await page.getByTestId("recommendation-text").innerText();

  // Edit the note.
  const note = `E2E note ${Date.now()}`;
  const field = page.getByLabel("Note to the borrower (optional)");
  await field.fill(note);
  await Promise.all([saved(), field.blur()]);

  await page.reload();
  await expect(selected).toHaveCount(2);
  await expect(page.getByRole("checkbox", { name: removedName! })).not.toBeChecked();
  await expect(selected.nth(1).getByRole("radio")).toBeChecked();
  await expect(page.getByTestId("recommendation-text")).toHaveText(recommendation);
  await expect(page.getByLabel("Note to the borrower (optional)")).toHaveValue(note);
  await expect(page.getByTestId("report-preview")).toContainText(note, PREVIEW);
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "ac6-sam-after-reload.png"),
    fullPage: true,
  });
});
