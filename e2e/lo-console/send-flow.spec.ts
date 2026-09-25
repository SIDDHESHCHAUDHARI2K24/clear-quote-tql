// CQ-020 unit 2: the Send tab's send flow against the real stack (API,
// Temporal worker, WeasyPrint, MinIO, Mailpit). Jordan Lee sends Marcus
// Hale's package, watches Rendering letter → Emailing → Done, gets the
// "Sent to {email}" toast, the header pill turns Sent and the "Sent
// versions" list shows it with a working PDF link. A second send makes v2
// and marks v1 Superseded (AC6 in the UI).
//
// Needs `make worker` running on this slot's task queue. Each run adds
// sent versions to Marcus's package (a send can't be undone); nothing
// here depends on how many already exist.
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { loConsoleApiBaseUrl } from "../helpers/env";
import { readEmailsSince } from "../helpers/mailpit";
import { openSendTabReady } from "../helpers/send";
import { staffLogin } from "../helpers/staffLogin";

const staffPassword = process.env.SEED_STAFF_PASSWORD;
test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

const LO_EMAIL = "jordan.lee@clearquote-demo.test";
const MARCUS_EMAIL = "marcus.hale@clearquote-demo.test";
const SUBJECT = "Your pre-approval and numbers from Total Quality Lending";
const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-020-letter-and-send/evidence");

test.describe.configure({ mode: "serial" });

async function sendFromTab(page: Page, buttonName: RegExp) {
  const sendButton = page.getByRole("button", { name: buttonName });
  await expect(sendButton).toBeEnabled({ timeout: 15_000 });
  await sendButton.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("send-recipient")).toHaveText(MARCUS_EMAIL);
  await dialog.getByRole("button", { name: "Send", exact: true }).click();
  return dialog;
}

test("sending shows progress, toasts, flips the pill to Sent and lists the version; a re-send supersedes it", async ({
  page,
}) => {
  test.setTimeout(90_000);
  flushLoginRateLimit();
  const applicationId = applicationIdByClientEmail(MARCUS_EMAIL);
  await page.setViewportSize({ width: 1280, height: 900 });
  await staffLogin(page, LO_EMAIL, staffPassword!);
  await openSendTabReady(page, applicationId);

  const since = new Date(Date.now() - 2_000);
  const dialog = await sendFromTab(page, /^Send to borrower$/);
  const progress = dialog.getByTestId("send-progress");
  await expect(progress).toContainText("Rendering letter");
  await expect(progress).toContainText("Emailing");
  await expect(progress.getByText("Done")).toBeVisible();
  await expect(dialog).toContainText("✓Done", { timeout: 30_000 });
  await expect(page.getByTestId("send-toast")).toHaveText(new RegExp(`Sent to ${MARCUS_EMAIL}`));
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "send-dialog-done-1280.png") });

  // Header pill (workspace summary refetch) and the package's sent state.
  await expect(page.locator('[data-status="sent"]')).toHaveText("Sent");
  const closeButtons = dialog.getByRole("button", { name: "Close" });
  await closeButtons.last().click();
  await expect(page.getByRole("button", { name: "Send to borrower" })).toBeEnabled();

  const versions = page.getByTestId("sent-version");
  await expect(versions.first()).toBeVisible();
  const newest = versions.first();
  await expect(newest.getByTestId("sent-version-state")).toHaveText("Current");
  const newestLabel = (await newest.locator("span.font-medium").first().textContent()) ?? "";
  const newestNumber = Number(newestLabel.replace(/\D/g, ""));
  expect(newestNumber).toBeGreaterThan(0);

  // The PDF link streams this version's letter from the API (staff cookie).
  const pdfHref = await newest.getByRole("link", { name: "Download PDF" }).getAttribute("href");
  expect(pdfHref).toBe(
    `${loConsoleApiBaseUrl()}/api/v1/packages/${await packageId(page, applicationId)}/letter.pdf?version=${newestNumber}`,
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
  await sendFromTab(page, /^Send to borrower$/);
  await expect(page.getByRole("dialog")).toContainText("✓Done", { timeout: 30_000 });
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).last().click();
  await expect(versions.first()).toContainText(`Version ${newestNumber + 1}`);
  await expect(versions.first().getByTestId("sent-version-state")).toHaveText("Current");
  await expect(versions.nth(1)).toContainText(`Version ${newestNumber}`);
  await expect(versions.nth(1).getByTestId("sent-version-state")).toHaveText("Superseded");
  await versions.nth(1).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "sent-versions-1280.png") });
});

async function packageId(page: Page, applicationId: string): Promise<string> {
  const response = await page.request.get(
    `${loConsoleApiBaseUrl()}/api/v1/applications/${applicationId}/package`,
  );
  return ((await response.json()) as { id: string }).id;
}
