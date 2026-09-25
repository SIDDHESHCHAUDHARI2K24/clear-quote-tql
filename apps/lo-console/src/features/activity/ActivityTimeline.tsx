"use client";

import { useEffect, useState } from "react";

import { EmptyState, Pagination, extractErrorMessage } from "@cq/ui";

import type { ActivityEvent } from "./api";
import { fetchActivity } from "./api";
import { categoryForEventType, iconForEventType } from "./icons";

export interface ActivityTimelineProps {
  /** Fetches `GET .../applications/{id}/activity` itself, paginated. Omit
   * when passing `events` instead. */
  applicationId?: string;
  /** CQ-026 (Clients, plan.md Decision 8): a pre-fetched, already-merged
   * event list (e.g. a client's activity across every application) --
   * renders directly, no fetch and no further pagination (the caller has
   * already capped it, e.g. at 50). Exactly one of `applicationId`/`events`
   * is expected per usage. */
  events?: ActivityEvent[];
}

interface DayGroup {
  key: string;
  label: string;
  events: ActivityEvent[];
}

// Local calendar date (not `toISOString().slice(0, 10)`, which is UTC) --
// code review finding: a UTC-keyed bucket disagrees with the
// locally-formatted heading/times for roughly a third of the day for any
// viewer not at UTC+0, splitting one local day across two headings.
function localDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dayLabel(iso: string): { key: string; label: string } {
  const date = new Date(iso);
  const key = localDateKey(date);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const todayKey = localDateKey(today);
  const yesterdayKey = localDateKey(yesterday);

  if (key === todayKey) return { key, label: "Today" };
  if (key === yesterdayKey) return { key, label: "Yesterday" };
  return {
    key,
    // Pinned locale (not the runtime default -- react-doctor's
    // no-locale-format-in-render): matches packages/ui/report/format.ts's
    // own convention, so server and client always render the same string.
    label: date.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }),
  };
}

function groupByDay(events: ActivityEvent[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const event of events) {
    const { key, label } = dayLabel(event.at);
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.events.push(event);
    } else {
      groups.push({ key, label, events: [event] });
    }
  }
  return groups;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; events: ActivityEvent[]; page: number; pageSize: number; total: number };

/** spec.md CQ-029 "Timeline": `GET .../activity`, grouped by day, one icon
 * per event-type category, system events visually quieter (AC1). Exported
 * for CQ-026's client-detail page (plan.md E9/Decision 8) to reuse either
 * by `applicationId` (fetches + paginates itself) or by a pre-fetched,
 * already-merged `events` list (no fetch, no further pagination). */
export function ActivityTimeline({ applicationId, events: givenEvents }: ActivityTimelineProps) {
  const [state, setState] = useState<LoadState>(
    givenEvents
      ? {
          kind: "ready",
          events: givenEvents,
          page: 1,
          pageSize: givenEvents.length,
          total: givenEvents.length,
        }
      : { kind: "loading" },
  );
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (givenEvents || !applicationId) return;
    let cancelled = false;
    setState({ kind: "loading" });
    fetchActivity(applicationId, page).then(({ data, error }) => {
      if (cancelled) return;
      if (error || !data) {
        setState({
          kind: "error",
          message: extractErrorMessage(error, "Couldn't load activity. Try again."),
        });
        return;
      }
      setState({
        kind: "ready",
        events: data.items,
        page: data.page,
        pageSize: data.page_size,
        total: data.total,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [applicationId, givenEvents, page]);

  if (state.kind === "loading") {
    return (
      <p className="text-sm text-neutral-600" role="status">
        Loading activity…
      </p>
    );
  }

  if (state.kind === "error") {
    return (
      <p role="alert" className="text-sm text-status-danger">
        {state.message}
      </p>
    );
  }

  if (state.events.length === 0) {
    return (
      <EmptyState title="No activity yet" body="Nothing has happened on this application yet." />
    );
  }

  const groups = groupByDay(state.events);

  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <div key={group.key}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            {group.label}
          </h3>
          <ul className="flex flex-col gap-2">
            {group.events.map((event) => {
              const isSystem = event.actor.kind === "system";
              return (
                <li
                  key={event.id}
                  data-category={categoryForEventType(event.type)}
                  className={
                    isSystem
                      ? "flex items-start gap-2 text-sm text-neutral-500"
                      : "flex items-start gap-2 text-sm text-navy-900"
                  }
                >
                  <span aria-hidden="true">{iconForEventType(event.type)}</span>
                  <div className="flex-1">
                    <p className={isSystem ? "font-normal" : "font-medium"}>{event.message}</p>
                    <p className="text-xs text-neutral-500">
                      {isSystem ? "System" : event.actor.name} · {formatTime(event.at)}
                    </p>
                    {event.payload_summary && (
                      <p className="text-xs text-neutral-400">{event.payload_summary}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      {state.total > state.pageSize && (
        <Pagination
          page={state.page}
          pageSize={state.pageSize}
          total={state.total}
          onChange={setPage}
          label="Activity pagination"
        />
      )}
    </div>
  );
}
