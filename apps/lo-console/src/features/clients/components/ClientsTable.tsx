"use client";

import { EmptyState, StatusPill } from "@cq/ui";

import { formatDate } from "../../applications";
import type { ClientRow } from "../types";

interface SortableHeader {
  key: string;
  label: string;
  /** `sort` value this header toggles to, or `undefined` for a column
   * with no server-side sort (e.g. Contact). */
  sortValue?: string;
  align?: "left" | "right" | "center";
}

const HEADERS: SortableHeader[] = [
  { key: "name", label: "Name", sortValue: "name" },
  { key: "contact", label: "Contact" },
  { key: "lo", label: "LO" },
  { key: "applications", label: "Applications", align: "center" },
  { key: "active_status", label: "Active status" },
  { key: "last_activity", label: "Last activity", sortValue: "-last_activity" },
];

export interface ClientsTableProps {
  rows: ClientRow[];
  sort: string;
  onSortChange: (sort: string) => void;
  onRowClick: (row: ClientRow) => void;
}

const CELL_CLASSES = "px-3 py-3 text-navy-900";

/** spec.md CQ-026 "Frontend": a sortable table of clients -- name, contact,
 * assigned LO, application count, active application status, last
 * activity. Mirrors `applications/components/ApplicationsTable.tsx`. */
export function ClientsTable({ rows, sort, onSortChange, onRowClick }: ClientsTableProps) {
  if (rows.length === 0) {
    return <EmptyState title="No clients match these filters" />;
  }

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-600">
          {HEADERS.map((header) => {
            const isActive = header.sortValue !== undefined && header.sortValue === sort;
            // Each sortable column here has exactly one `sortValue` (spec.md
            // CQ-026 "Backend": only `name`, `-created_at`, `-last_activity`
            // are valid), so its direction is fixed by its own leading `-`
            // -- not derived from the currently-active `sort` string (that
            // would mislabel `name`, which is always ascending, as
            // "descending" whenever it happened to be the active column;
            // code review finding).
            const direction = header.sortValue?.startsWith("-") ? "descending" : "ascending";
            const alignClass =
              header.align === "right"
                ? "text-right"
                : header.align === "center"
                  ? "text-center"
                  : "text-left";
            return (
              <th
                key={header.key}
                scope="col"
                aria-sort={header.sortValue ? (isActive ? direction : "none") : undefined}
                className={`px-3 py-2 font-medium ${alignClass}`}
              >
                {header.sortValue ? (
                  <button
                    type="button"
                    onClick={() => onSortChange(header.sortValue!)}
                    className="inline-flex items-center gap-1 hover:text-navy-900"
                  >
                    {header.label}
                    {isActive && (
                      <span aria-hidden="true">{direction === "descending" ? "▾" : "▴"}</span>
                    )}
                  </button>
                ) : (
                  header.label
                )}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.id}
            data-client-id={row.id}
            onClick={() => onRowClick(row)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onRowClick(row);
              }
            }}
            tabIndex={0}
            role="button"
            className="cursor-pointer border-b border-neutral-100 hover:bg-neutral-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-navy-500"
          >
            <td className={CELL_CLASSES}>{row.name}</td>
            <td className={`${CELL_CLASSES} text-neutral-600`}>
              <div className="flex flex-col">
                <span>{row.email}</span>
                {row.phone && <span className="text-xs text-neutral-500">{row.phone}</span>}
              </div>
            </td>
            <td className={CELL_CLASSES}>{row.lo_name}</td>
            <td className={`${CELL_CLASSES} text-center`}>{row.application_count}</td>
            <td className={CELL_CLASSES}>
              {row.active_status ? (
                <StatusPill status={row.active_status} size="sm" />
              ) : (
                <span className="text-neutral-400">—</span>
              )}
            </td>
            <td className={`${CELL_CLASSES} text-neutral-600`}>
              {row.last_activity ? formatDate(row.last_activity) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
