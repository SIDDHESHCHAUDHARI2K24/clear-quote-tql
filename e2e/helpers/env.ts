import { readFileSync } from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "../..");

// Reads the LO console's own `NEXT_PUBLIC_API_URL` (written by
// `scripts/worktree-env.sh <slot>` into `apps/lo-console/.env.local`), so a
// spec can call the API directly (e.g. to trigger the pipeline) without
// hardcoding a port that differs per worktree slot.
export function loConsoleApiBaseUrl(): string {
  const envPath = path.join(REPO_ROOT, "apps/lo-console/.env.local");
  const content = readFileSync(envPath, "utf-8");
  const match = content.match(/^NEXT_PUBLIC_API_URL=(.+)$/m);
  if (!match) {
    throw new Error(`Could not find NEXT_PUBLIC_API_URL in ${envPath}`);
  }
  return match[1].trim();
}

// CQ-034 spec.md AC4: same idea as `loConsoleApiBaseUrl`, for the Borrower
// Portal's own `.env.local` -- lets a spec drive `POST /api/v1/portal/
// support` directly (e.g. to reach the 6th request fast) without
// hardcoding a port that differs per worktree slot.
export function portalApiBaseUrl(): string {
  const envPath = path.join(REPO_ROOT, "apps/borrower-portal/.env.local");
  const content = readFileSync(envPath, "utf-8");
  const match = content.match(/^NEXT_PUBLIC_API_URL=(.+)$/m);
  if (!match) {
    throw new Error(`Could not find NEXT_PUBLIC_API_URL in ${envPath}`);
  }
  return match[1].trim();
}
