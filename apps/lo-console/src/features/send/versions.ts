// Display helpers for the "Sent versions" list (no money fields).

const SENT_AT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function formatSentAt(iso: string): string {
  return SENT_AT.format(new Date(iso));
}

/** The Outbox viewer is CQ-029 (P5/P6); until it lands this route 404s
 * (plan.md Decision 17). */
export function outboxHref(outboxEmailId: string): string {
  return `/outbox?email=${encodeURIComponent(outboxEmailId)}`;
}
