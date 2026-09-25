// Frontend display unions. String values are pinned to match CQ-007's
// Postgres enums (`FieldSource`, `application_status`) exactly, so the
// generated api-client types need no translation layer. CQ-007 owns the
// backend names; this file mirrors them.

export type ApplicationStatus =
  | "intake"
  | "verifying"
  | "needs_attention"
  | "ready_to_price"
  | "priced"
  | "sent"
  | "viewed"
  | "option_selected"
  | "inquiry"
  | "stale"
  | "withdrawn"
  | "closed";

export const APPLICATION_STATUSES: readonly ApplicationStatus[] = [
  "intake",
  "verifying",
  "needs_attention",
  "ready_to_price",
  "priced",
  "sent",
  "viewed",
  "option_selected",
  "inquiry",
  "stale",
  "withdrawn",
  "closed",
];

export type StatusTone = "neutral" | "info" | "danger" | "success" | "warning";

// Fixed tone map — see spec.md "StatusPill" component contract.
export const APPLICATION_STATUS_TONE: Record<ApplicationStatus, StatusTone> = {
  intake: "neutral",
  verifying: "info",
  needs_attention: "danger",
  ready_to_price: "info",
  priced: "success",
  sent: "info",
  viewed: "info",
  option_selected: "success",
  inquiry: "warning",
  stale: "warning",
  withdrawn: "neutral",
  closed: "success",
};

export type SourceBadgeSource =
  | "encompass"
  | "rentcast"
  | "airdna"
  | "smartasset"
  | "steadily"
  | "optimal_blue"
  | "credit_bureau"
  | "property_search"
  | "lo_entry"
  | "formula"
  | "default"
  | "lo_override";

export const SOURCE_BADGE_SOURCES: readonly SourceBadgeSource[] = [
  "encompass",
  "rentcast",
  "airdna",
  "smartasset",
  "steadily",
  "optimal_blue",
  "credit_bureau",
  "property_search",
  "lo_entry",
  "formula",
  "default",
  "lo_override",
];
