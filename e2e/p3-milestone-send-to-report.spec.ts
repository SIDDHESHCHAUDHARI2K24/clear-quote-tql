// P3 milestone (CQ-020 AC1 end to end, and a re-check of CQ-022 AC1):
// Jordan Lee sends Marcus Hale's package from the LO console; the email
// lands in Mailpit with the PDF attached; its "See your numbers" link opens
// the borrower portal, which asks Marcus to sign in (password + email OTP,
// H2: no magic link) and then lands on his report.
//
// Drives both apps, so it runs in `playwright.config.ts`'s `cross-app`
// project with `LO_BASE_URL`/`PORTAL_BASE_URL` as full URLs. Needs
// `make worker` running on this slot's task queue.
import path from "node:path";

import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "./helpers/db";
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
