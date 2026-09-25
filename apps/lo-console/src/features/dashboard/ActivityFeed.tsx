import Link from "next/link";

import { Card, EmptyState } from "@cq/ui";

import type { ActivityItem } from "./api";

export interface ActivityFeedProps {
  items: ActivityItem[];
}

function relativeTime(at: string): string {
  const diffMs = Date.now() - new Date(at).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function typeLabel(type: string): string {
  return type.replace(/[._]/g, " ");
}

// spec.md: "Recent activity" -- the latest 20 activity events across the
// LO's applications (actor, type, application, time).
export function ActivityFeed({ items }: ActivityFeedProps) {
  return (
    <Card title="Recent activity">
      {items.length === 0 ? (
        <EmptyState title="Nothing needs you right now" headingLevel={3} />
      ) : (
        <ul className="flex flex-col divide-y divide-neutral-200">
          {items.map((item) => (
            <li key={item.id} className="py-3 first:pt-0 last:pb-0">
              <Link
                href={`/applications/${item.application_id}`}
                className="flex items-center justify-between gap-2 rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-500"
              >
                <span className="text-sm text-navy-900">
                  <span className="font-medium">{item.actor}</span>{" "}
                  <span className="text-neutral-600">{typeLabel(item.type)}</span>{" "}
                  <span className="text-neutral-500">&middot; {item.client_name}</span>
                </span>
                <span className="shrink-0 text-xs text-neutral-500">{relativeTime(item.at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
