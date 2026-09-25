"use client";

import { formatPercent } from "@cq/ui";
import { useState } from "react";

import { formatMoneyCents } from "../pricing/format";
import type { ProductRow } from "./api";

type SortKey =
  | "investor_name"
  | "product_name"
  | "note_rate"
  | "price_pct"
  | "points_pct"
  | "monthly_pi"
  | "lock_period_days";

interface Column {
  key: SortKey;
  label: string;
  numeric: boolean;
  render: (row: ProductRow) => string;
}

const COLUMNS: Column[] = [
  { key: "investor_name", label: "Investor", numeric: false, render: (r) => r.investor_name },
  { key: "product_name", label: "Product", numeric: false, render: (r) => r.product_name },
  { key: "note_rate", label: "Rate", numeric: true, render: (r) => formatPercent(r.note_rate) },
  { key: "price_pct", label: "Price", numeric: true, render: (r) => r.price_pct },
  {
    key: "points_pct",
    label: "Points",
    numeric: true,
    render: (r) => (r.points_pct != null ? formatPercent(r.points_pct) : "—"),
  },
  { key: "monthly_pi", label: "P&I", numeric: true, render: (r) => formatMoneyCents(r.monthly_pi) },
  {
    key: "lock_period_days",
    label: "Lock days",
    numeric: true,
    render: (r) => String(r.lock_period_days),
  },
];

// Ordering only (no arithmetic on any money/rate value): `<`/`>` on the
// decimal strings' numeric values.
function compareValues(a: unknown, b: unknown, numeric: boolean): number {
  if (numeric) {
    const x = Number(a ?? 0);
    const y = Number(b ?? 0);
    if (x < y) return -1;
    if (x > y) return 1;
    return 0;
  }
  return String(a ?? "").localeCompare(String(b ?? ""));
}

function rowKey(row: ProductRow): string {
  return `${row.investor_name}|${row.product_name}|${row.lock_period_days}|${row.note_rate}`;
}

export interface ManualGridProps {
  rows: ProductRow[];
  busy: boolean;
  onChoose: (row: ProductRow) => void;
}

/** "Choose manually": the full mock OB result grid, sortable, with the par
 * and buydown rows tagged. Choosing a row saves it as a quote. */
export function ManualGrid({ rows, busy, onChoose }: ManualGridProps) {
  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({
    key: "note_rate",
    direction: "asc",
  });
  const column = COLUMNS.find((c) => c.key === sort.key) ?? COLUMNS[2];
  const sorted = [...rows].sort((a, b) => {
    const order = compareValues(a[sort.key], b[sort.key], column.numeric);
    return sort.direction === "asc" ? order : -order;
  });

  const toggle = (key: SortKey) =>
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "asc" },
    );

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm" aria-label="Priced products">
        <thead>
          <tr className="border-b border-neutral-200 text-left text-neutral-600">
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                scope="col"
                aria-sort={
                  sort.key === c.key
                    ? sort.direction === "asc"
                      ? "ascending"
                      : "descending"
                    : "none"
                }
                className={`px-3 py-2 font-medium ${c.numeric ? "text-right" : ""}`}
              >
                <button type="button" onClick={() => toggle(c.key)} className="font-medium">
                  {c.label}
                </button>
              </th>
            ))}
            <th scope="col" className="px-3 py-2">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)} className="border-b border-neutral-100" data-testid="product-row">
              {COLUMNS.map((c) => (
                <td
                  key={c.key}
                  className={`px-3 py-2 text-navy-900 ${c.numeric ? "num text-right" : ""}`}
                >
                  {c.render(row)}
                  {c.key === "product_name" && row.is_par_rate && (
                    <span className="ml-2 rounded bg-navy-50 px-1.5 text-xs text-navy-700">
                      Par
                    </span>
                  )}
                  {c.key === "product_name" && row.is_buydown_rate && (
                    <span className="ml-2 rounded bg-sage-50 px-1.5 text-xs text-sage-700">
                      Buydown
                    </span>
                  )}
                </td>
              ))}
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onChoose(row)}
                  aria-label={`Choose ${row.investor_name} ${row.product_name} at ${formatPercent(row.note_rate)}`}
                  className="rounded-md border border-neutral-200 px-2 py-1 text-xs font-medium text-navy-900"
                >
                  Choose
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
