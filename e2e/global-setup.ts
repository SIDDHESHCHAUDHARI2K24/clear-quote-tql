import path from "node:path";
import fs from "node:fs";

import { chromium, type FullConfig } from "@playwright/test";

import { borrowerLogin } from "./helpers/borrowerLogin";

// CQ-022: signs each borrower persona the report specs need in **once**,
// here, and saves the resulting session cookie (Playwright `storageState`)
// to a file each spec then loads via `test.use({ storageState: ... })`.
//
// Why: `report-option-switch.spec.ts`, `report-print.spec.ts` and
// `report-mobile.spec.ts` all need a signed-in Luis Romero (the only
// seeded, non-expired, multi-option persona -- see those specs' own
// comments). A fresh `borrowerLogin` per spec file burns one of the
// borrower login rate limit's 5-per-15-minutes attempts per email
// (`backend/app/core/config.py::login_rate_limit_per_email`) each; three
// specs plus `report-login-redirect.spec.ts`'s own two real logins would
// sit right at that ceiling on every run, breaking on the first retry.
// Logging in once here and reusing the saved session drops that to a
// single real login per full suite run for the shared personas.
//
// `report-login-redirect.spec.ts` deliberately does its own real logins
// (that's the whole point of that spec) and never applies this
// storageState, so it isn't affected.
const AUTH_DIR = path.join(__dirname, ".auth");

export const LUIS_ROMERO_STORAGE_STATE = path.join(AUTH_DIR, "luis-romero.json");
export const GRACE_KIM_STORAGE_STATE = path.join(AUTH_DIR, "grace-kim.json");
// CQ-023: Kathleen McReynolds is the one TBD persona (buy-box FL/[Davenport,
// Orlando]) -- `report-matches.spec.ts` needs her signed in the same
// once-per-suite way, after `backend/scripts/freeze_version.py
// --persona kathleen_mcreynolds` has given her a real sent version.
export const KATHLEEN_MCREYNOLDS_STORAGE_STATE = path.join(AUTH_DIR, "kathleen-mcreynolds.json");

const PERSONAS: Array<{ email: string; storageStatePath: string }> = [
  { email: "luis.romero@clearquote-demo.test", storageStatePath: LUIS_ROMERO_STORAGE_STATE },
  { email: "grace.kim@clearquote-demo.test", storageStatePath: GRACE_KIM_STORAGE_STATE },
  {
    email: "kathleen.mcreynolds@clearquote-demo.test",
    storageStatePath: KATHLEEN_MCREYNOLDS_STORAGE_STATE,
  },
];

export default async function globalSetup(config: FullConfig): Promise<void> {
  const password = process.env.SEED_BORROWER_PASSWORD;
  if (!password) {
    // Mirrors every report-*.spec.ts's own `test.skip(!password, ...)` --
    // smoke-only runs (no seeded stack) don't need any of this.
    return;
  }

  const portalProject = config.projects.find((p) => p.name === "borrower-portal");
  const baseURL = portalProject?.use.baseURL ?? process.env.PORTAL_BASE_URL;
  if (!baseURL) return;

  fs.mkdirSync(AUTH_DIR, { recursive: true });

  const browser = await chromium.launch();
  try {
    for (const persona of PERSONAS) {
      await loginWithRetry(browser, baseURL, persona.email, password, persona.storageStatePath);
    }
  } finally {
    await browser.close();
  }
}

// The dev Next.js server can be slow to compile `/login` on a cold first
// hit (observed directly: a fresh page occasionally times out waiting for
// the OTP step to render, while a retry against the now-compiled route
// succeeds immediately) -- this only ever runs against a real dev server
// (never a production build), so a small retry here is cheap insurance
// against that, not a sign of a flaky assertion.
async function loginWithRetry(
  browser: import("@playwright/test").Browser,
  baseURL: string,
  email: string,
  password: string,
  storageStatePath: string,
  attempts = 3,
): Promise<void> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    const page = await browser.newPage({ baseURL });
    try {
      await borrowerLogin(page, email, password);
      await page.context().storageState({ path: storageStatePath });
      return;
    } catch (error) {
      lastError = error;
    } finally {
      await page.close();
    }
  }
  throw lastError;
}
