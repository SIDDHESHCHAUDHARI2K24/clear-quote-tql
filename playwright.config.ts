import { defineConfig, devices } from "@playwright/test";

// P3/P4 foundation (H3, docs/backlog/phase-p3-p4-foundation.md): shared
// Playwright config for both apps. Each item under `e2e/lo-console/` or
// `e2e/borrower-portal/` writes the specs its own spec.md's ACs name;
// this file only owns process-wide config (projects, base URLs, reporter).
//
// Base URLs come from env so each worker's worktree (scripts/worktree-env.sh
// <slot>) points Playwright at its own running apps instead of the shared
// dev ports (3010/3020) -- see docs/backlog/phase-p3-p4-plan.md's "E2E
// recipe". Infra (API, Next dev servers) is started by hand per the recipe;
// this config never spawns a `webServer` itself, since a worktree's API,
// worker and two Next apps all need their own env/ports set up first.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"]],
  // CQ-022: signs the shared borrower personas in once (see its own
  // comment) instead of once per report-*.spec.ts file, so a full run
  // stays well under the borrower login rate limit.
  globalSetup: "./e2e/global-setup.ts",
  use: {
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "lo-console",
      testDir: "./e2e/lo-console",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: process.env.LO_BASE_URL ?? "http://localhost:3010",
      },
    },
    {
      name: "borrower-portal",
      testDir: "./e2e/borrower-portal",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: process.env.PORTAL_BASE_URL ?? "http://localhost:3020",
      },
    },
  ],
});
