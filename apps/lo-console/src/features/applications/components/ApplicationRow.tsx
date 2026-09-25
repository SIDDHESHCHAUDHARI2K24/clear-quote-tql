"use client";

import { StatusPill } from "@cq/ui";

import { formatDate, formatMoney } from "../format";
import type { ApplicationListRow } from "../types";

export interface ApplicationRowProps {
  row: ApplicationListRow;
  onClick?: (row: ApplicationListRow) => void;
}

const STRATEGY_LABEL: Record<ApplicationListRow["strategy"], string> = {
  primary: "Primary",
  ltr: "LTR",
  str: "STR",
};

const CELL_CLASSES = "px-3 py-3 text-navy-900";

/**
 * spec.md CQ-027 "Row" / plan.md E9: one `<tr>` for `GET /applications`'s
 * row shape. Owned here so CQ-026 (Clients, wave 3) can render the exact
 * same row -- client name, property label, strategy, purchase price,
 * status pill, open-flag badge, assigned LO, updated at -- inside its own
 * `<table>` rather than redefining it.
 */
export function ApplicationRow({ row, onClick }: ApplicationRowProps) {
  const clickable = Boolean(onClick);

  return (
    <tr
      data-application-id={row.id}
      onClick={clickable ? () => onClick?.(row) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.(row);
              }
            }
          : undefined
      }
      tabIndex={clickable ? 0 : undefined}
      role={clickable ? "button" : undefined}
      className={
        clickable
          ? "cursor-pointer border-b border-neutral-100 hover:bg-neutral-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-navy-500"
          : "border-b border-neutral-100"
      }
    >
      <td className={CELL_CLASSES}>{row.client_name}</td>
      <td className={`${CELL_CLASSES} text-neutral-600`}>{row.property_label ?? "—"}</td>
      <td className={CELL_CLASSES}>{STRATEGY_LABEL[row.strategy]}</td>
      <td className={`${CELL_CLASSES} num text-right`}>{formatMoney(row.purchase_price)}</td>
      <td className={CELL_CLASSES}>
        <StatusPill status={row.status} size="sm" />
      </td>
      <td className={`${CELL_CLASSES} text-center`}>
        {row.flag_count > 0 && (
          <span
            aria-label={`${row.flag_count} open flag${row.flag_count === 1 ? "" : "s"}`}
            className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-status-danger px-1.5 text-xs font-medium text-neutral-0"
          >
            {row.flag_count}
          </span>
        )}
      </td>
      <td className={CELL_CLASSES}>{row.lo_name}</td>
      <td className={`${CELL_CLASSES} text-neutral-600`}>{formatDate(row.updated_at)}</td>
    </tr>
  );
}
