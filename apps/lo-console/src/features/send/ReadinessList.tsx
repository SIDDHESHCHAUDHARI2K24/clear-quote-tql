import Link from "next/link";

import type { Readiness } from "./api";

const TAB_NAMES: Record<string, string> = {
  borrowers: "Borrowers",
  housing: "Housing",
  credit: "Credit",
  assets: "Assets",
  property: "Property",
  pricing: "Pricing",
  send: "Send",
};

export interface ReadinessListProps {
  applicationId: string;
  readiness: Readiness | null;
}

/** What still blocks sending, each linked to the tab that fixes it. */
export function ReadinessList({ applicationId, readiness }: ReadinessListProps) {
  if (readiness === null) {
    return <p className="text-sm text-neutral-600">Checking readiness…</p>;
  }
  if (readiness.ready) {
    return (
      <p role="status" className="text-sm font-medium text-status-success">
        Ready to send
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-navy-900">Before you can send</h3>
      <ul className="flex flex-col gap-2" data-testid="readiness-blockers">
        {readiness.blockers.map((blocker) => (
          <li
            key={`${blocker.code}:${blocker.message}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-status-danger/40 bg-status-danger/5 px-3 py-2 text-sm text-navy-900"
          >
            <span>{blocker.message}</span>
            {blocker.tab !== "send" && (
              <Link
                href={`/applications/${applicationId}/${blocker.tab}`}
                className="font-medium text-navy-700 underline"
              >
                Go to {TAB_NAMES[blocker.tab] ?? blocker.tab}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
