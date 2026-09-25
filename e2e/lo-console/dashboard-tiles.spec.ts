import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { applicationIdByClientEmail, flushLoginRateLimit } from "../helpers/db";
import { staffLogin } from "../helpers/staffLogin";

// CQ-025 spec.md. Needs `.env`'s SEED_STAFF_PASSWORD and `make
// demo-reset`'s seeded personas (seed/personas/*.yaml).
const password = process.env.SEED_STAFF_PASSWORD;
const ADMIN = "riley.admin@clearquote-demo.test";
const EVIDENCE = "docs/backlog/evidence/CQ-025-dashboard";
const REPO_ROOT = path.resolve(__dirname, "../..");

test.skip(!password, "SEED_STAFF_PASSWORD not set -- run make demo-reset and export it first");

test.describe.configure({ mode: "serial" });

test.beforeEach(() => {
  flushLoginRateLimit();
});

function psql(sql: string): void {
  execFileSync(
    "docker",
    [
      "compose",
      "-f",
      "infra/docker-compose.yml",
      "exec",
      "-T",
      "postgres",
      "psql",
      "-U",
      "cq",
      "-d",
      process.env.DATABASE_URL!.split("/").pop()!,
      "-c",
      sql,
    ],
    { cwd: REPO_ROOT },
  );
}

test("tiles are links with the spec.md query parameters (AC4 -- pending, re-check once CQ-027 exists)", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);

  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();

  // Scoped to the tiles region -- the shell nav has its own "Clients" and
  // "Applications" links with the same accessible names.
  const tiles = page.getByRole("region", { name: "Dashboard tiles" });

  const expectedHrefs: Record<string, string> = {
    Clients: "/clients",
    Applications: "/applications",
    "Pre-approvals sent": "/applications?status=sent_or_later",
    "With a property": "/applications?has_property=true",
    "Awaiting your review": "/applications?status=Priced,Inquiry,OptionSelected",
    "Needs attention": "/applications?status=NeedsAttention",
    "Stale quotes": "/applications?status=Stale",
  };

  for (const [label, href] of Object.entries(expectedHrefs)) {
    const link = tiles.getByRole("link", { name: new RegExp(`${label}$`) });
    await expect(link).toHaveAttribute("href", href);
  }
  await page.screenshot({ path: `${EVIDENCE}/dashboard-tiles.png` });
});

test("Aisha, Luis and Grace show up in the right lists with their reasons (AC3)", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);

  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();

  const attention = page
    .getByRole("heading", { level: 3, name: "Needs your attention" })
    .locator("xpath=ancestor::section");
  await expect(attention.getByText("Aisha Coleman")).toBeVisible();
  await expect(attention.getByText("Cannot price: missing Occupancy")).toBeVisible();
  await expect(attention.getByText("Luis Romero")).toBeVisible();

  const stale = page
    .getByRole("heading", { level: 3, name: "Going stale" })
    .locator("xpath=ancestor::section");
  await expect(stale.getByText("Grace Kim")).toBeVisible();
});

test("resolving a flag directly in the DB removes the application from the attention list (AC5 -- pending, re-check once CQ-028 exists)", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await staffLogin(page, ADMIN, password!);

  const attention = page
    .getByRole("heading", { level: 3, name: "Needs your attention" })
    .locator("xpath=ancestor::section");
  await expect(attention.getByText("Aisha Coleman")).toBeVisible();

  // CQ-028's real re-verify endpoint doesn't exist yet -- resolve directly
  // in the DB, per the coordinator's E2E note, mirroring what a real
  // re-verify would do once all of an application's blocking flags clear
  // (resolve the flag, move the status off NeedsAttention).
  const applicationId = applicationIdByClientEmail("aisha.coleman@clearquote-demo.test");
  psql(`update flags set resolved_at = now() where application_id = '${applicationId}';`);
  psql(`update applications set status = 'ready_to_price' where id = '${applicationId}';`);

  // 30s poll would eventually pick this up; reload to assert deterministically.
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  await expect(attention.getByText("Aisha Coleman")).toHaveCount(0);
});
