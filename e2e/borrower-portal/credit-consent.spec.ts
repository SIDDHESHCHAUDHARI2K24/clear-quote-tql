import path from "node:path";

import { expect, request as playwrightRequest, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

import { borrowerLogin } from "../helpers/borrowerLogin";
import { applicationIdByClientEmail, closeDbPool, flushLoginRateLimit } from "../helpers/db";
import { portalApiBaseUrl } from "../helpers/env";
import { readOtpCode, waitForEmails } from "../helpers/mailpit";

// CQ-033 AC1/AC7 end to end (slot 23, docs/backlog/phase-p5-p6-worker-guide.md):
// the LO asks for a hard pull through the API, Tom Brandt opens the link
// from the Mailpit email, authorizes with his typed name, and the LO's
// Credit section reports Authorized with the middle-of-three FICO (690).
// The API must run with PORTAL_BASE_URL pointing at this portal so the
// emailed link lands here.
const REPO_ROOT = path.resolve(__dirname, "../..");
const EVIDENCE_DIR = path.join(REPO_ROOT, "docs/backlog/CQ-033-hard-pull-consent/evidence");
const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://localhost:8025";

const borrowerPassword = process.env.SEED_BORROWER_PASSWORD;
const staffPassword = process.env.SEED_STAFF_PASSWORD;
const BORROWER_EMAIL = "tom.brandt@clearquote-demo.test";
const MANAGER_EMAIL = "casey.nguyen@clearquote-demo.test";
const REQUEST_SUBJECT = "Please authorize a credit check";
const AUTHORIZED_SUBJECT = "Credit check authorized — FICO 690";

test.skip(
  !borrowerPassword || !staffPassword,
  "SEED_BORROWER_PASSWORD / SEED_STAFF_PASSWORD not set -- run make demo-reset and export them",
);

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

test.afterAll(async () => {
  await closeDbPool();
});

async function staffApi(apiBaseUrl: string): Promise<APIRequestContext> {
  const ctx = await playwrightRequest.newContext({ baseURL: apiBaseUrl });
  const login = await ctx.post("/api/v1/auth/staff/login", {
    data: { email: MANAGER_EMAIL, password: staffPassword },
  });
  expect(login.status(), await login.text()).toBe(200);
  const { challenge_id: challengeId } = (await login.json()) as { challenge_id: string };
  const code = await readOtpCode(MANAGER_EMAIL);
  const verify = await ctx.post("/api/v1/auth/staff/otp/verify", {
    data: { challenge_id: challengeId, code },
  });
  expect(verify.status(), await verify.text()).toBe(200);
  return ctx;
}

async function countSince(subject: string, sinceIso: string): Promise<number> {
  const query = encodeURIComponent(`subject:"${subject}"`);
  const response = await fetch(`${MAILPIT_URL}/api/v1/search?query=${query}&limit=50`);
  const { messages } = (await response.json()) as { messages: { Created: string }[] };
  return messages.filter((m) => new Date(m.Created) >= new Date(sinceIso)).length;
}

async function expectNoHorizontalScroll(page: Page) {
  const [scrollWidth, clientWidth] = await Promise.all([
    page.evaluate(() => document.documentElement.scrollWidth),
    page.evaluate(() => document.documentElement.clientWidth),
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
}

test("AC1: LO requests, Tom Brandt authorizes from the email link, Credit shows FICO 690", async ({
  page,
}) => {
  const apiBaseUrl = portalApiBaseUrl();
  const applicationId = applicationIdByClientEmail(BORROWER_EMAIL);
  await borrowerLogin(page, BORROWER_EMAIL, borrowerPassword!);
  const staff = await staffApi(apiBaseUrl);

  // A pending request left by an earlier run blocks a new one (409); the
  // borrower declines it first so the run starts clean.
  let requested = await staff.post(
    `/api/v1/applications/${applicationId}/credit/hard-pull-request`,
  );
  if (requested.status() === 409) {
    const section = await staff.get(`/api/v1/applications/${applicationId}/sections/credit`);
    const stale = ((await section.json()) as { credit: { consent: { id: string } } }).credit
      .consent;
    await page.request.post(`${apiBaseUrl}/api/v1/portal/consents/${stale.id}/decline`, {
      data: { reason: "e2e reset" },
    });
    requested = await staff.post(`/api/v1/applications/${applicationId}/credit/hard-pull-request`);
  }
  expect(requested.status(), await requested.text()).toBe(201);
  const consentId = ((await requested.json()) as { consent: { id: string } }).consent.id;
  const since = new Date(Date.now() - 1000).toISOString();

  // The borrower opens the link from the request email.
  const emails = await waitForEmails(BORROWER_EMAIL, REQUEST_SUBJECT);
  const email = emails.find((m) => m.HTML.includes(consentId));
  expect(email, "request email for this consent").toBeTruthy();
  const link = email!.HTML.match(/href="([^"]*\/tasks\/credit-check\/[^"]+)"/)![1];
  await page.goto(link.replace(/&amp;/g, "&"));

  await expect(
    page.getByRole("heading", { level: 1, name: "Authorize a credit check" }),
  ).toBeVisible();
  await expect(page.getByText(/Experian, Equifax and TransUnion/).first()).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "consent-form-1280.png"), fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "consent-form-375.png"), fullPage: true });

  // AC7: both inputs are required; submitting empty shows linked errors.
  await page.getByRole("button", { name: "Authorize" }).click();
  await expect(page.getByText("Check the box to authorize the credit check.")).toBeVisible();

  await page.getByRole("checkbox", { name: /I authorize/ }).check();
  await page.getByLabel("Type your full name to sign").fill("Tom Brandt");
  await page.getByRole("button", { name: "Authorize" }).click();

  await expect(page.getByRole("heading", { name: "Credit check authorized" })).toBeVisible({
    timeout: 15_000,
  });
  await expectNoHorizontalScroll(page);
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "consent-authorized-375.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "consent-authorized-1280.png"),
    fullPage: true,
  });

  // E11: the LO's Credit section shows Authorized with the hard-pull FICO.
  const section = await staff.get(`/api/v1/applications/${applicationId}/sections/credit`);
  const credit = (
    (await section.json()) as {
      credit: {
        representative_fico: number;
        pull_type: string;
        consent: { id: string; status: string; fico_after_pull: number | null };
      };
    }
  ).credit;
  expect(credit.representative_fico).toBe(690);
  expect(credit.pull_type).toBe("hard_pull");
  expect(credit.consent.id).toBe(consentId);
  expect(credit.consent.status).toBe("accepted");
  expect(credit.consent.fico_after_pull).toBe(690);

  // The LO gets exactly one "authorized" email for this run.
  await expect.poll(() => countSince(AUTHORIZED_SUBJECT, since), { timeout: 10_000 }).toBe(1);

  // Reopening the link shows the confirmation, not the form (no second pull).
  await page.goto(link.replace(/&amp;/g, "&"));
  await expect(page.getByRole("heading", { name: "Credit check authorized" })).toBeVisible();
  await staff.dispose();
});
