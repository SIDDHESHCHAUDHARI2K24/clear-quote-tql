import Link from "next/link";

import { Card, EmptyState, StatusPill } from "@cq/ui";
import type { ApplicationStatus } from "@cq/ui";

import type { AttentionItem } from "./api";

export interface AttentionListProps {
  items: AttentionItem[];
}

function ageLabel(days: number): string {
  if (days <= 0) return "today";
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

// spec.md: "Needs your attention" -- NeedsAttention, Inquiry or
// OptionSelected, oldest status change first, each with client name,
// status, reason and age.
export function AttentionList({ items }: AttentionListProps) {
  return (
    <Card title="Needs your attention">
      {items.length === 0 ? (
        <EmptyState title="Nothing needs you right now" headingLevel={3} />
      ) : (
        <ul className="flex flex-col divide-y divide-neutral-200">
          {items.map((item) => (
            <li key={item.application_id} className="py-3 first:pt-0 last:pb-0">
              <Link
                href={`/applications/${item.application_id}`}
                className="flex flex-col gap-1 rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-500"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-navy-900">{item.client_name}</span>
                  <StatusPill status={item.status as ApplicationStatus} size="sm" />
                </div>
                <p className="text-sm text-neutral-600">{item.reason}</p>
                <span className="text-xs text-neutral-500">{ageLabel(item.age_days)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
