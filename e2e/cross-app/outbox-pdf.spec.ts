import path from "node:path";

import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { openSendTabReady } from "../helpers/send";
import { staffLogin } from "../helpers/staffLogin";

// P56 U4 (phase-p5-p6-verification.md, CQ-029 spec.md AC2's own PDF-download
// half): "opening Marcus Hale's quote email shows the HTML and downloads the
// PDF." post-dev.md had this `pending -- re-check after CQ-020` because no
// persona had both a real quote email and a real PDF attachment yet; CQ-020
// has since merged (Marcus Hale is now sent for real by
// `e2e/p3-milestone-send-to-report.spec.ts`), so this spec is the real
// re-check: as the LO, send his package through the Send tab (with the
// worker running so the real pipeline renders the PDF), then use the LO
// console's own `/outbox` (CQ-029) -- not Mailpit -- to open that email and
// download the attachment.
//
// This project (`cross-app`, playwright.config.ts) has no `baseURL` of its
// own (like `e2e/p3-milestone-send-to-report.spec.ts`'s own "LO send flow"
// test in the same project), so this drives the LO console via its own
// `browser.newContext({ baseURL: LO_BASE_URL })` rather than the default
// `page` fixture, which would try to resolve every relative `page.goto`
// against no base at all.
//
// Note (found while writing this spec, not fixed -- out of scope): the Send
// tab's own "Open in Outbox" link builds `/outbox?email=<id>`
// (apps/lo-console/src/features/send/versions.ts:18), but `/outbox`'s page
// only reads `?email_id=` (apps/lo-console/src/app/(staff)/outbox/page.tsx:
// 18) -- that link's target drawer never auto-opens. Worked around here by
// navigating straight to `/outbox?application_id=<id>` and clicking the row
// instead of following that link.
//
// Second note (also found here, also not fixed -- out of scope, already a
// logged follow-up): `outbox/service.py`'s `_TYPE_SUBJECT_RULES["quote_sent"]`
// (backend/app/features/notifications/outbox/service.py:49) only matches a
// subject containing "pre-approval is ready", but CQ-020's real send subject
// (`delivery/email_template.py`) is "Your pre-approval and numbers from
// Total Quality Lending" -- no match, so this row's Type column reads
// "Other", not "Quote sent", even after the merge. Filters on subject text
// below instead of the Type column for that reason.
//
// Needs `.env`'s SEED_STAFF_PASSWORD, `make demo-reset`'s seeded Marcus
// Hale (priced), and a running API + `make worker` on this worktree's slot
// (the send flow's letter-render + email steps run as real Temporal
// activities, like `e2e/p3-milestone-send-to-report.spec.ts`).
const staffPassword = process.env.SEED_STAFF_PASSWORD;
test.skip(!staffPassword, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

const LO_EMAIL = "jordan.lee@clearquote-demo.test";
const MARCUS_EMAIL = "marcus.hale@clearquote-demo.test";
const LO_BASE_URL = process.env.LO_BASE_URL ?? "http://localhost:3010";
const EVIDENCE_DIR = path.resolve(
  __dirname,
  "../../docs/backlog/CQ-029-timeline-outbox-panel/evidence",
);

test.describe.configure({ mode: "serial" });

test("CQ-029 AC2: sending Marcus Hale's quote lands in the Outbox with the HTML shown and the PDF downloadable", async ({
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

  // 1. LO console: send (worker must be running for the real pipeline to
  // render the PDF and record the outbox row).
  await staffLogin(page, LO_EMAIL, staffPassword!);
  await openSendTabReady(page, applicationId);
  const sendButton = page.getByRole("button", { name: "Send to borrower" });
  await expect(sendButton).toBeEnabled({ timeout: 15_000 });
  await sendButton.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Send", exact: true }).click();
  await expect(dialog).toContainText("✓Done", { timeout: 30_000 });
  await dialog.getByRole("button", { name: "Close" }).last().click();

  // 2. Outbox: scoped to Marcus's application (OutboxList's `applicationId`
  // prop), find the quote-sent email and open its detail drawer. Filters
  // on the subject text, not the Type column ("Quote sent") -- see the
  // second note above, this row's Type still reads "Other" today.
  await page.goto(`/outbox?application_id=${applicationId}`);
  await expect(page.getByRole("heading", { name: "Outbox" })).toBeVisible();
  const row = page
    .locator("tbody tr")
    .filter({ hasText: MARCUS_EMAIL })
    .filter({ hasText: "pre-approval and numbers" })
    .first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.click();

  // 3. Detail drawer: the HTML body renders in the sandboxed iframe (AC7),
  // and the PDF attachment link is there.
  const frame = page.frameLocator('iframe[title^="Email:"]');
  await expect(frame.locator("body")).toContainText(/numbers/i, { timeout: 10_000 });
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "outbox-marcus-quote-email.png"),
    fullPage: true,
  });

  const pdfLink = page.getByRole("link", { name: "preapproval-letter.pdf" });
  await expect(pdfLink).toBeVisible();
  const pdfHref = await pdfLink.getAttribute("href");
  expect(pdfHref).toBeTruthy();

  // 4. Download it: a real PDF, non-empty, over the same route the link
  // uses (core/storage.py's `get_object` stream, staff cookie via
  // `page.request`'s shared context).
  const pdf = await page.request.get(pdfHref!);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toContain("application/pdf");
  const body = await pdf.body();
  expect(body.length).toBeGreaterThan(0);
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");

  await context.close();
});
