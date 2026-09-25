import { expect, test } from "@playwright/test";

import { staffLogin } from "../helpers/staffLogin";

// Proves the `staffLogin` helper (email/password + Mailpit-read OTP) works
// end to end against a real running stack -- needs `.env`'s
// SEED_STAFF_PASSWORD and a seeded LO (make demo-reset). The brief for this
// unit named `lo@clearquote.test`, but seed/users.yaml (CQ-010) actually
// seeds `jordan.lee@clearquote-demo.test` as its first LO ("Jordan Lee") --
// no `lo@clearquote.test` account exists, so this uses the real seeded
// address instead (logged as a deviation in
// docs/backlog/phase-p3-p4-foundation.md). Skipped unless
// SEED_STAFF_PASSWORD is set so `make e2e` still runs the pure smoke specs
// without a fully seeded stack.
const email = "jordan.lee@clearquote-demo.test";
const password = process.env.SEED_STAFF_PASSWORD;

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test("staff can sign in with email + password + emailed OTP", async ({ page }) => {
  await staffLogin(page, email, password!);
  await expect(page).toHaveURL("/");
});
