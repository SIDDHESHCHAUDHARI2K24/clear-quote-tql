// Mirrors `ApplicationStatus` (backend/app/core/enums.py). The generated
// api-client types `LatestApplicationOut.status` as a plain `string` (the
// OpenAPI schema doesn't narrow it to the enum), so this is a defensive
// lookup: an unrecognized status falls back to the raw value rather than
// throwing or rendering nothing.
const APPLICATION_STATUS_LABELS: Record<string, string> = {
  intake: "Application received",
  verifying: "In review",
  needs_attention: "In review",
  ready_to_price: "In review",
  priced: "Pre-approved",
  sent: "Pre-approved",
  viewed: "Pre-approved",
  option_selected: "Option selected",
  inquiry: "Question sent to your loan officer",
  stale: "Numbers expired",
  withdrawn: "Withdrawn",
  closed: "Closed",
};

export function applicationStatusLabel(status: string): string {
  return APPLICATION_STATUS_LABELS[status] ?? status;
}
