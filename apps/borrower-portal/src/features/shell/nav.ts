import { safeNextPath } from "../../lib/nextParam";

// P5/P6 foundation (E6): the portal header nav, in order.
export const PORTAL_NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/support", label: "Support" },
] as const;

// Placeholder licensing text until real TQL details exist (CQ-035/036).
export const NMLS_PLACEHOLDER = "NMLS #0000000 (placeholder)";

/** `/login`, or `/login?next=<path>` for any protected path but `/`
 * (mirrors `src/middleware.ts`, which also leaves `next` off for `/`). */
export function loginUrlFor(path: string): string {
  const next = safeNextPath(path);
  if (!next || next === "/") return "/login";
  return `/login?next=${encodeURIComponent(next)}`;
}
