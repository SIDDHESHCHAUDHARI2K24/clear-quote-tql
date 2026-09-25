// P3 milestone (CQ-020 AC1 end to end, and a re-check of CQ-022 AC1):
// Jordan Lee sends Marcus Hale's package from the LO console; the email
// lands in Mailpit with the PDF attached; its "See your numbers" link opens
// the borrower portal, which asks Marcus to sign in (password + email OTP,
// H2: no magic link) and then lands on his report.
//
// The second test is the LO console's own send flow (progress, toast, pill,
// Sent versions, PDF link, re-send supersedes).
//
// Both tests send Marcus Hale's package, so they live in one serial file:
// in two files under `fullyParallel` one send could supersede the other's
// version or be read as the other's email. They run in `playwright.config.
// ts`'s `cross-app` project (it drives both apps, with `LO_BASE_URL`/
// `PORTAL_BASE_URL` as full URLs). `openSendTabReady` re-prices Marcus if
// an earlier pricing spec left his quotes stale; a pricing spec editing
// him *during* a send can still fail that send (run with `--workers 1` for
// evidence). Not a project dependency on purpose: a failed lo-console spec
// would then skip these. Needs `make worker`
// running on this slot's task queue. Every run adds sent versions to
// Marcus's package; nothing here depends on how many already exist.
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "./helpers/db";
import { loConsoleApiBaseUrl } from "./helpers/env";
import { readEmailsSince, readOtpCode } from "./helpers/mailpit";
import { openSendTabReady } from "./helpers/send";
import { staffLogin } from "./helpers/staffLogin";

const staffPassword = process.env.SEED_STAFF_PASSWORD;
const borrowerPassword = process.env.SEED_BORROWER_PASSWORD;
test.skip(
  !staffPassword || !borrowerPassword,
  "SEED_STAFF_PASSWORD/SEED_BORROWER_PASSWORD not set -- run make demo-reset and export them first",
);

const LO_EMAIL = "jordan.lee@clearquote-demo.test";
const MARCUS_EMAIL = "marcus.hale@clearquote-demo.test";
const SUBJECT = "Your pre-approval and numbers from Total Quality Lending";
const LO_BASE_URL = process.env.LO_BASE_URL ?? "http://localhost:3010";
const PORTAL_BASE_URL = process.env.PORTAL_BASE_URL ?? "http://localhost:3020";
const EVIDENCE_DIR = path.resolve(__dirname, "../docs/backlog/CQ-020-letter-and-send/evidence");

test.describe.configure({ mode: "serial" });

test("P3: send Marcus Hale's package, open the emailed link, sign in, land on his report", async ({
  browser,
}) => {
  test.setTimeout(120_000);
  flushLoginRateLimit();
  const applicationId = applicationIdByClientEmail(MARCUS_EMAIL);

  // 1. LO console: send.
  const loContext = await browser.newContext({
    baseURL: LO_BASE_URL,
    viewport: { width: 1280, height: 900 },
  });
  const lo = await loContext.newPage();
  await staffLogin(lo, LO_EMAIL, staffPassword!);
  await openSendTabReady(lo, applicationId);
  await lo.screenshot({ path: path.join(EVIDENCE_DIR, "p3-1-send-tab-ready-1280.png") });

  const since = new Date(Date.now() - 2_000);
  await lo.getByRole("button", { name: /^Send to borrower$/ }).click();
  const dialog = lo.getByRole("dialog");
  await dialog.getByRole("button", { name: "Send", exact: true }).click();
  await expect(dialog).toContainText("✓Done", { timeout: 30_000 });
  await expect(lo.getByTestId("send-toast")).toContainText(`Sent to ${MARCUS_EMAIL}`);
  await expect(lo.locator('[data-status="sent"]')).toHaveText("Sent");
  await lo.screenshot({ path: path.join(EVIDENCE_DIR, "p3-2-sent-toast-1280.png") });

  // 2. Mailpit: exactly one new email to Marcus, with the PDF.
  const [email] = await readEmailsSince(MARCUS_EMAIL, SUBJECT, since);
  expect(email.Attachments.map((a) => a.FileName)).toEqual(["preapproval-letter.pdf"]);
  const link = /href="([^"]+\/report\/[^"]+)"[^>]*>\s*See your numbers/i.exec(email.HTML)?.[1];
  expect(link, "the email's See your numbers link").toBeTruthy();
  const reportUrl = link!.replace(/&amp;/g, "&");
  expect(reportUrl.startsWith(`${PORTAL_BASE_URL}/report/`)).toBe(true);
  expect(email.Text).toContain(reportUrl);

  // 3. Borrower portal: the link asks for sign-in, then shows the report.
  const portalContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const portal = await portalContext.newPage();
  await portal.goto(reportUrl);
  const reportPath = new URL(reportUrl).pathname;
  await expect(portal).toHaveURL(`${PORTAL_BASE_URL}/login?next=${encodeURIComponent(reportPath)}`);
  await portal.getByLabel("Email").fill(MARCUS_EMAIL);
  await portal.getByLabel("Password").fill(borrowerPassword!);
  await portal.getByRole("button", { name: "Sign in" }).click();
  await expect(portal.getByLabel("Verification code")).toBeVisible();
  await portal.getByLabel("Verification code").fill(await readOtpCode(MARCUS_EMAIL));
  await portal.getByRole("button", { name: "Verify" }).click();

  await portal.waitForURL(reportUrl);
  await expect(portal.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();
  await expect(portal.getByText(/newer version of your numbers/i)).toHaveCount(0);
  await portal.screenshot({
    path: path.join(EVIDENCE_DIR, "p3-3-marcus-report-1280.png"),
    fullPage: true,
  });

  await portalContext.close();
  await loContext.close();
});

async function sendFromTab(page: Page) {
  const sendButton = page.getByRole("button", { name: "Send to borrower" });
  await expect(sendButton).toBeEnabled({ timeout: 15_000 });
  await sendButton.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("send-recipient")).toHaveText(MARCUS_EMAIL);
  await dialog.getByRole("button", { name: "Send", exact: true }).click();
  return dialog;
}

test("LO send flow: progress, toast, Sent pill, Sent versions with a PDF; a re-send supersedes", async ({
  browser,
}) => {
  test.setTimeout(90_000);
  flushLoginRateLimit();
  const applicationId = applicationIdByClientEmail(MARCUS_EMAIL);
  const context = await browser.newContext({
    baseURL: LO_BASE_URL,
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();
  await staffLogin(page, LO_EMAIL, staffPassword!);
  await openSendTabReady(page, applicationId);

  const since = new Date(Date.now() - 2_000);
  const dialog = await sendFromTab(page);
  const progress = dialog.getByTestId("send-progress");
  await expect(progress).toContainText("Rendering letter");
  await expect(progress).toContainText("Emailing");
  await expect(dialog).toContainText("✓Done", { timeout: 30_000 });
  await expect(page.getByTestId("send-toast")).toHaveText(new RegExp(`Sent to ${MARCUS_EMAIL}`));
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "send-dialog-done-1280.png") });

  // Header pill (workspace summary refetch).
  await expect(page.locator('[data-status="sent"]')).toHaveText("Sent");
  await dialog.getByRole("button", { name: "Close" }).last().click();
  await expect(page.getByRole("button", { name: "Send to borrower" })).toBeEnabled();

  const versions = page.getByTestId("sent-version");
  const newest = versions.first();
  await expect(newest.getByTestId("sent-version-state")).toHaveText("Current");
  const newestLabel = (await newest.locator("span.font-medium").first().textContent()) ?? "";
  const newestNumber = Number(newestLabel.replace(/\D/g, ""));
  expect(newestNumber).toBeGreaterThan(0);

  // The PDF link streams this version's letter from the API (staff cookie).
  const pkg = await page.request.get(
    `${loConsoleApiBaseUrl()}/api/v1/applications/${applicationId}/package`,
  );
  const packageId = ((await pkg.json()) as { id: string }).id;
  const pdfHref = await newest.getByRole("link", { name: "Download PDF" }).getAttribute("href");
  expect(pdfHref).toBe(
    `${loConsoleApiBaseUrl()}/api/v1/packages/${packageId}/letter.pdf?version=${newestNumber}`,
  );
  const pdf = await page.request.get(pdfHref!);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toContain("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  await expect(newest.getByRole("link", { name: "Open in Outbox" })).toHaveAttribute(
    "href",
    /^\/outbox\?email=[0-9a-f-]{36}$/,
  );

  // One email in Mailpit for this send, with the PDF attached.
  const [email] = await readEmailsSince(MARCUS_EMAIL, SUBJECT, since);
  expect(email.Attachments.map((a) => a.FileName)).toContain("preapproval-letter.pdf");

  // Re-send: a new current version, the previous one superseded.
  const again = await sendFromTab(page);
  await expect(again).toContainText("✓Done", { timeout: 30_000 });
  await again.getByRole("button", { name: "Close" }).last().click();
  await expect(versions.first()).toContainText(`Version ${newestNumber + 1}`);
  await expect(versions.first().getByTestId("sent-version-state")).toHaveText("Current");
  await expect(versions.nth(1)).toContainText(`Version ${newestNumber}`);
  await expect(versions.nth(1).getByTestId("sent-version-state")).toHaveText("Superseded");
  await versions.nth(1).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "sent-versions-1280.png") });

  await context.close();
});
