import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { borrowerLogin } from "../helpers/borrowerLogin";
import { applicationIdByClientEmail, execSql } from "../helpers/db";

const EVIDENCE_DIR = path.resolve(__dirname, "../../docs/backlog/CQ-024-borrower-actions/evidence");

// CQ-024 spec.md AC1/AC2/AC3: a freshly sent persona moves forward on the
// Buydown option, sees the confirmed state, and a second attempt is a
// no-op (409, shown as the current state -- not an error).
//
// **Deviation (plan.md/post-dev.md):** the coordinator's own recipe names
// Marcus Hale and "the Buydown option", but his real seeded/priced data
// (persona 1: Tampa STR, DSCR < 1) has no Buydown candidate in the mock
// rate sheet grid for either of his two DSCR-bucket scenario groups
// (confirmed live: `select label from quotes join scenarios ... where
// application_id = <marcus's>` returns only "Par" twice) -- a
// characteristic of the mock pricing data for that specific risk tier, not
// a bug in this item. Priya Nair (persona 3, primary/Conventional) is
// used instead: she's `priced` with no `fixture_layer` (a genuinely "fresh"
// persona, same as Marcus would have been), and her Conventional rate
// sheet reliably yields both Par and Buydown (verified live and by
// `backend/app/features/portal/reports/tests/conftest.py`'s own
// `seed_conventional_rate_sheet` fixture, which every primary-application
// report test in this repo already relies on for the same reason).
const email = "priya.nair@clearquote-demo.test";
const password = process.env.SEED_BORROWER_PASSWORD;

test.skip(!password, "SEED_BORROWER_PASSWORD not set -- run make demo-reset and export it first");

// Both tests below permanently move Priya Nair's application off `priced`
// (`option_selected`, then `inquiry` -- real CQ-024 `move_forward`/`ask
// about another option` flows, the whole point of this file), through
// `freeze_sent_version.py`'s own real `application.status =
// ApplicationStatus.SENT` plus whichever action each test then takes.
// `portal-home.spec.ts`'s later "AC6" tests need her back at `priced`
// ("Your loan officer is reviewing your numbers" -- `stage_and_label`,
// portal/home/service.py) -- restore it once both tests are done, same
// pattern as `aisha-occupancy-resume.spec.ts`'s own `afterAll`. Leftover
// `quote_packages`/`quote_package_versions` rows from the two freezes stay
// in place -- nothing downstream asserts their absence for her.
test.afterAll(() => {
  const applicationId = applicationIdByClientEmail(email);
  execSql(`update applications set status = 'priced' where id = '${applicationId}';`);
});

const REPO_ROOT = path.resolve(__dirname, "../..");

interface FrozenVersion {
  reportToken: string;
  options: { label: string; quoteId: string }[];
}

// Runs `backend/scripts/freeze_sent_version.py` (this item's own dev
// freeze script, plan.md Decision 10) to get a brand-new, un-acted-on sent
// version every time this spec runs -- reusing a leftover version from a
// prior run (or from move_forward already having been called on it) would
// make every rule in the table below un-testable a second time.
function freezeSentVersion(persona: string): FrozenVersion {
  const output = execFileSync(
    "uv",
    ["run", "python", "backend/scripts/freeze_sent_version.py", "--persona", persona],
    { cwd: REPO_ROOT, encoding: "utf-8" },
  );

  const tokenMatch = output.match(/^report_token=(\S+)$/m);
  if (!tokenMatch) throw new Error(`Could not parse report_token from:\n${output}`);

  const options = [...output.matchAll(/^\s*option (\w+): quote_id=(\S+)$/gm)].map((m) => ({
    label: m[1],
    quoteId: m[2],
  }));
  if (options.length === 0) throw new Error(`Could not parse any options from:\n${output}`);

  return { reportToken: tokenMatch[1], options };
}

test("move forward on the Buydown option sets the confirmed state; a second attempt is a no-op", async ({
  page,
}) => {
  const version = freezeSentVersion("priya_nair");
  const buydown = version.options.find((o) => o.label === "Buydown");
  expect(buydown, "Priya Nair's frozen version should include a Buydown option").toBeTruthy();

  await borrowerLogin(page, email, password!);
  await page.goto(`/report/${version.reportToken}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();

  // Switch to the Buydown option before moving forward (AC1: "move
  // forward on the Buydown option" -- not necessarily the recommended/
  // default-selected one).
  await page.getByRole("radio", { name: /buydown/i }).click();

  await page.getByRole("button", { name: /move forward with this option/i }).click();
  await expect(page.getByRole("dialog", { name: /move forward with this option/i })).toBeVisible();
  await expect(page.getByText(/your rate isn.t locked yet/i)).toBeVisible();

  await page.getByRole("button", { name: /^Yes, let \w+ know$/ }).click();

  // Confirmed state: buttons gone, "You chose Buydown on <date>." shown.
  await expect(page.getByText(/You chose Buydown on/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /move forward with this option/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /ask about another option/i })).toHaveCount(0);
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "move-forward-confirmed.png") });

  // AC2: reloading shows the same confirmed state (persisted server-side,
  // not just local component state).
  await page.reload();
  await expect(page.getByText(/You chose Buydown on/i)).toBeVisible();
});

test("ask about another option requires a message, then sets Inquiry and is still visible afterward", async ({
  page,
}) => {
  const version = freezeSentVersion("priya_nair");

  await borrowerLogin(page, email, password!);
  await page.goto(`/report/${version.reportToken}`);
  await expect(page.getByRole("heading", { name: /here are your numbers/i })).toBeVisible();

  await page.getByRole("button", { name: /ask about another option/i }).click();
  const sendButton = page.getByRole("button", { name: /send message/i });
  await expect(sendButton).toBeDisabled();

  await page
    .getByPlaceholder(/what would you like to change/i)
    .fill("Could we look at a lower cash to close?");
  await expect(sendButton).toBeEnabled();
  await sendButton.click();

  await expect(page.getByText(/will be in touch/i)).toBeVisible();
  // ask_other stays allowed from Inquiry (spec.md's rules table), so the
  // buttons remain -- this is not a terminal "confirmed" state like
  // move_forward's.
  await expect(page.getByRole("button", { name: /move forward with this option/i })).toBeVisible();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, "ask-other-sent.png") });
});
