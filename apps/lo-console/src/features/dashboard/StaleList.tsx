import Link from "next/link";

import { Card, EmptyState } from "@cq/ui";

import type { StaleItem } from "./api";

export interface StaleListProps {
  items: StaleItem[];
}

// spec.md: "Going stale" -- the recommended quote or latest sent version is
// older than 21 days, with days old.
export function StaleList({ items }: StaleListProps) {
  return (
    <Card title="Going stale">
      {items.length === 0 ? (
        <EmptyState title="Nothing needs you right now" headingLevel={3} />
      ) : (
        <ul className="flex flex-col divide-y divide-neutral-200">
          {items.map((item) => (
            <li key={item.application_id} className="py-3 first:pt-0 last:pb-0">
              <Link
                href={`/applications/${item.application_id}`}
                className="flex items-center justify-between gap-2 rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-500"
              >
                <span className="font-medium text-navy-900">{item.client_name}</span>
                <span className="text-sm tabular-nums text-neutral-600">
                  {item.days_old} days old
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
