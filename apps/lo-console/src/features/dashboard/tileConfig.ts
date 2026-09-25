import type { DashboardTiles } from "./api";

export interface TileConfig {
  key: keyof DashboardTiles;
  label: string;
  href: string;
}

// spec.md's tile table, verbatim (E10 -- CQ-027 uses these exact
// parameter names once it exists: `sent_or_later`, the `status` comma
// lists, `has_property=true`).
export const TILE_CONFIG: readonly TileConfig[] = [
  { key: "clients", label: "Clients", href: "/clients" },
  { key: "applications", label: "Applications", href: "/applications" },
  {
    key: "pre_approvals_sent",
    label: "Pre-approvals sent",
    href: "/applications?status=sent_or_later",
  },
  { key: "with_property", label: "With a property", href: "/applications?has_property=true" },
  {
    key: "awaiting_review",
    label: "Awaiting your review",
    href: "/applications?status=Priced,Inquiry,OptionSelected",
  },
  { key: "needs_attention", label: "Needs attention", href: "/applications?status=NeedsAttention" },
  { key: "stale_quotes", label: "Stale quotes", href: "/applications?status=Stale" },
];

/**
 * Appends `lo_id` to a tile's href when a Manager/Admin has one LO
 * selected, so the destination list matches the tile's (also `lo_id`-
 * scoped) count.
 */
export function tileHref(href: string, loId: string | null): string {
  if (!loId) return href;
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}lo_id=${loId}`;
}
