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

/** Deep-links into the CQ-029 Outbox viewer, which reads `?email_id=`
 * (apps/lo-console/src/app/(staff)/outbox/page.tsx). */
export function outboxHref(outboxEmailId: string): string {
  return `/outbox?email_id=${encodeURIComponent(outboxEmailId)}`;
}
