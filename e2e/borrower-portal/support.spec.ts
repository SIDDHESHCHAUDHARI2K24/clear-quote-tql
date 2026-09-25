import path from "node:path";

import { expect, test } from "@playwright/test";

import { borrowerLogin } from "../helpers/borrowerLogin";
import {
  borrowerAccountIdByEmail,
  closeDbPool,
  flushLoginRateLimit,
  flushSupportRateLimit,
} from "../helpers/db";
import { portalApiBaseUrl } from "../helpers/env";
import { waitForEmails } from "../helpers/mailpit";

// CQ-034 spec.md AC1/AC2/AC4: Marcus Hale (persona 1, priced -- seeded
// `marcus.hale@clearquote-demo.test`) submits a "quote" question through
// the UI; Mailpit shows exactly one email to the support inbox and one
// confirmation to him, both carrying the same reference. A 6th request in
// an hour is rate-limited (429), shown in the UI as "Please try again
// later".
const email = "marcus.hale@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");

const SUPPORT_INBOX = process.env.SUPPORT_INBOX ?? "support@tql.local";
const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-034-support-form/evidence");

// Both tests submit as the same persona and read Mailpit for that
// mailbox; `fullyParallel: true` would let them race on which submission's
// "newest matching subject" is whose. Serial keeps them from overlapping.
// It also means the rate-limit test's flush (test 2) never wipes out a
// counter test 1's own submission is relying on.
test.describe.configure({ mode: "serial" });

test.afterAll(async () => {
  await closeDbPool();
});

test("submitting a quote question emails the support inbox and the borrower, with the same reference", async ({
  page,
}) => {
  const borrowerAccountId = borrowerAccountIdByEmail(email);
  flushSupportRateLimit(borrowerAccountId);
  flushLoginRateLimit();

  await borrowerLogin(page, email, password!);
  await page.goto("/support");

  await expect(page.getByRole("heading", { name: "Get in touch" })).toBeVisible();
  await page.getByLabel("What's this about?").selectOption("quote");
  await page
    .getByLabel("Message")
    .fill("I have a question about the buydown option on my latest quote.");
  await page.getByRole("button", { name: /send message/i }).click();

  await expect(page.getByText(/your reference is/i)).toBeVisible();
  const referenceText = await page.getByText(/SUP-[A-Z0-9]+/).textContent();
  const referenceMatch = /SUP-[A-Z0-9]+/.exec(referenceText ?? "");
  expect(referenceMatch, `Could not find a SUP- reference in "${referenceText}"`).toBeTruthy();
  const reference = referenceMatch![0];
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "support-confirmation-1280.png") });

  const inboxEmails = await waitForEmails(SUPPORT_INBOX, reference);
  expect(inboxEmails).toHaveLength(1);
  expect(inboxEmails[0].Subject).toContain(reference);
  expect(inboxEmails[0].Subject).toContain("quote");
  expect(inboxEmails[0].HTML).toContain("Marcus Hale");

  const confirmationEmails = await waitForEmails(email, reference);
  expect(confirmationEmails).toHaveLength(1);
  expect(confirmationEmails[0].Subject).toContain(reference);
  expect(confirmationEmails[0].HTML).toContain(reference);

  // Worker guide's evidence convention: 1280px + 375px for portal pages.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "support-confirmation-375.png") });
});

test("a 6th request in an hour is rate-limited, shown as 'Please try again later'", async ({
  page,
}) => {
  const borrowerAccountId = borrowerAccountIdByEmail(email);
  flushSupportRateLimit(borrowerAccountId);
  flushLoginRateLimit();

  await borrowerLogin(page, email, password!);

  const apiBaseUrl = portalApiBaseUrl();
  const body = {
    topic: "other",
    message: "Just checking in on the status of my file, thanks.",
    preferred_contact: "email",
  };

  // Reach the limit fast via direct API calls (the browser context's
  // cookie jar already carries the session `borrowerLogin` established,
  // so these count against the same borrower as the UI submission below).
  for (let i = 0; i < 5; i += 1) {
    const response = await page.request.post(`${apiBaseUrl}/api/v1/portal/support`, {
      data: body,
    });
    expect(response.status(), `request ${i + 1} of 5 should succeed`).toBe(200);
  }

  // The 6th, through the actual form -- AC4 requires the page itself to
  // show the message, not just the API's status code.
  await page.goto("/support");
  await page.getByLabel("Message").fill(body.message);
  await page.getByRole("button", { name: /send message/i }).click();

  // `getByRole("alert")` alone also matches Next's own route announcer
  // (`#__next-route-announcer__`, always present, empty text) -- scope to
  // the one with the expected text.
  await expect(page.getByRole("alert").filter({ hasText: "Please try again later" })).toBeVisible();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "support-rate-limited-1280.png") });
});
