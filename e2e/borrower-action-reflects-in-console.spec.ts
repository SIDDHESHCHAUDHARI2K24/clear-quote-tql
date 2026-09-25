import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { flushLoginRateLimit } from "./helpers/db";
import { borrowerLogin } from "./helpers/borrowerLogin";
import { staffLogin } from "./helpers/staffLogin";

// CQ-024 AC6 (spec.md): the borrower moves forward in the Borrower Portal;
// the LO Console's application header shows Option selected after its
// poll. Drives both apps in one test, so it lives at the repo root
// (`playwright.config.ts`'s `cross-app` project) rather than under either
// app's own `e2e/<app>/` directory.
//
// **Decision (plan.md):** `WorkspaceProvider` (CQ-016,
// `apps/lo-console/src/features/workspace/WorkspaceProvider.tsx`) only
// auto-polls `GET .../summary` on its own 3s interval while `last_
// pipeline_stage` is *non-terminal* -- by design, that interval exists for
// the pipeline-progress banner (spec.md CQ-016 AC7), not for status
// changes from other sources. Every persona this item can use has already
// finished its pipeline (`last_pipeline_stage` lands on a terminal value,
// `priced`/`needs_attention`/etc. -- `docs/backlog/phase-p3-p4-foundation.
// md` D7), so the 3s interval is already stopped by the time a borrower
// acts. This test therefore triggers the LO console's *own* `refetch()`
// (the exact function the 3s interval itself calls) by navigating to the
// workspace a second time after the borrower's action, instead of waiting
// on an interval that CQ-016 deliberately never restarts once terminal.
// The header still reflects the change through the identical `GET .../
// summary` code path a live poll would use -- see plan.md for the full
// decision and a note on the underlying gap as a CQ-016/025 follow-up.
const borrowerEmail = "priya.nair@clearquote-demo.test";
const borrowerPassword = process.env.SEED_BORROWER_PASSWORD;
const loEmail = "jordan.lee@clearquote-demo.test";
const loPassword = process.env.SEED_STAFF_PASSWORD;

test.skip(
  !borrowerPassword || !loPassword,
  "SEED_BORROWER_PASSWORD/SEED_STAFF_PASSWORD not set -- run make demo-reset and export them first",
);

const REPO_ROOT = path.resolve(__dirname, "..");
const EVIDENCE_DIR = path.join(REPO_ROOT, "docs/backlog/CQ-024-borrower-actions/evidence");
const PORTAL_BASE_URL = process.env.PORTAL_BASE_URL ?? "http://localhost:3020";
const LO_BASE_URL = process.env.LO_BASE_URL ?? "http://localhost:3010";

function freezeSentVersionAndGetApplicationId(persona: string): {
  reportToken: string;
  applicationId: string;
  buydownQuoteId: string;
} {
  const output = execFileSync(
    "uv",
    ["run", "python", "backend/scripts/freeze_sent_version.py", "--persona", persona],
    { cwd: REPO_ROOT, encoding: "utf-8" },
  );
  const applicationIdMatch = output.match(/^application_id=(\S+)$/m);
  const tokenMatch = output.match(/^report_token=(\S+)$/m);
  const buydownMatch = output.match(/^\s*option Buydown: quote_id=(\S+)$/m);
  if (!applicationIdMatch || !tokenMatch || !buydownMatch) {
    throw new Error(`Could not parse freeze_sent_version.py output:\n${output}`);
  }
  return {
    applicationId: applicationIdMatch[1],
    reportToken: tokenMatch[1],
    buydownQuoteId: buydownMatch[1],
  };
}

test("borrower moves forward; the LO console header shows Option selected after its next load", async ({
  browser,
}) => {
  flushLoginRateLimit();
  const { reportToken, applicationId } = freezeSentVersionAndGetApplicationId("priya_nair");

  const loContext = await browser.newContext({ baseURL: LO_BASE_URL });
  const loPage = await loContext.newPage();
  await staffLogin(loPage, loEmail, loPassword!);
  await loPage.goto(`/applications/${applicationId}`);
  await loPage.waitForURL(new RegExp(`applications/${applicationId}/\\w+`));
  await expect(loPage.getByText("Sent")).toBeVisible();
  await loPage.screenshot({ path: path.join(EVIDENCE_DIR, "lo-console-before-sent.png") });

  const portalContext = await browser.newContext({ baseURL: PORTAL_BASE_URL });
  const portalPage = await portalContext.newPage();
  await borrowerLogin(portalPage, borrowerEmail, borrowerPassword!);
  await portalPage.goto(`/report/${reportToken}`);
  await expect(portalPage.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();

  await portalPage.getByRole("radio", { name: /buydown/i }).click();
  await portalPage.getByRole("button", { name: /move forward with this option/i }).click();
  await portalPage.getByRole("button", { name: /^Yes, let \w+ know$/ }).click();
  await expect(portalPage.getByText(/You chose Buydown on/i)).toBeVisible();

  // Re-navigate (see the Decision above): this is the same `GET .../
  // summary` request the 3s poll would make, run once here since the
  // pipeline is already terminal for this persona.
  await loPage.goto(`/applications/${applicationId}`);
  await loPage.waitForURL(new RegExp(`applications/${applicationId}/\\w+`));
  await expect(loPage.getByText("Option selected")).toBeVisible();
  await loPage.screenshot({
    path: path.join(EVIDENCE_DIR, "lo-console-after-option-selected.png"),
  });

  await portalContext.close();
  await loContext.close();
});
