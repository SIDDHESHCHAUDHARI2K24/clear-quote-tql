"use client";

import { EmptyState } from "@cq/ui";

import type { ApplicationListRow } from "../types";
import { ApplicationRow } from "./ApplicationRow";

interface SortableHeader {
  key: string;
  label: string;
  /** `sort` values this header toggles between (ascending, descending), or
   * a single value for a column with only one direction (e.g. `client`).
   * Omitted for a column with no server-side sort (e.g. Property). */
  sortValues?: [string] | [string, string];
  align?: "left" | "right" | "center";
}

const HEADERS: SortableHeader[] = [
  { key: "client", label: "Client", sortValues: ["client"] },
  { key: "property", label: "Property" },
  { key: "strategy", label: "Strategy" },
  { key: "amount", label: "Purchase price", sortValues: ["amount", "-amount"], align: "right" },
  { key: "status", label: "Status", sortValues: ["status"] },
  { key: "flags", label: "Flags", align: "center" },
  { key: "lo", label: "LO" },
  { key: "updated_at", label: "Updated", sortValues: ["-updated_at", "updated_at"] },
];

export interface ApplicationsTableProps {
  rows: ApplicationListRow[];
  sort: string;
  onSortChange: (sort: string) => void;
  onRowClick: (row: ApplicationListRow) => void;
}

function nextSort(header: SortableHeader, current: string): string | null {
  if (!header.sortValues) return null;
  if (header.sortValues.length === 1) return header.sortValues[0];
  const [asc, desc] = header.sortValues;
  return current === asc ? desc : asc;
}

export function ApplicationsTable({
  rows,
  sort,
  onSortChange,
  onRowClick,
}: ApplicationsTableProps) {
  if (rows.length === 0) {
    return <EmptyState title="No applications match these filters" />;
  }

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-600">
          {HEADERS.map((header) => {
            const target = nextSort(header, sort);
            const isActive = target !== null && (header.sortValues?.includes(sort) ?? false);
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
                aria-sort={
                  target
                    ? isActive
                      ? sort.startsWith("-")
                        ? "descending"
                        : "ascending"
                      : "none"
                    : undefined
                }
                className={`px-3 py-2 font-medium ${alignClass}`}
              >
                {target ? (
                  <button
                    type="button"
                    onClick={() => onSortChange(target)}
                    className="inline-flex items-center gap-1 hover:text-navy-900"
                  >
                    {header.label}
                    {isActive && <span aria-hidden="true">{sort.startsWith("-") ? "▾" : "▴"}</span>}
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
          <ApplicationRow key={row.id} row={row} onClick={onRowClick} />
        ))}
      </tbody>
    </table>
  );
}
