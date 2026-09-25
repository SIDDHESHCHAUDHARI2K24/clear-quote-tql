import type { ReactNode } from "react";

import { cx } from "../../utils/cx";

export interface TableColumn<T> {
  key: string;
  header: ReactNode;
  align?: "left" | "right" | "center";
  render?: (row: T) => ReactNode;
}

export interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyState?: ReactNode;
  density?: "compact" | "comfortable";
}

const ALIGN_CLASSES: Record<NonNullable<TableColumn<unknown>["align"]>, string> = {
  left: "text-left",
  right: "text-right num",
  center: "text-center",
};

const DENSITY_CLASSES: Record<NonNullable<TableProps<unknown>["density"]>, string> = {
  compact: "py-1.5",
  comfortable: "py-3",
};

export function Table<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  emptyState,
  density = "comfortable",
}: TableProps<T>) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-neutral-200 p-6 text-center text-neutral-600">
        {emptyState ?? "No data"}
      </div>
    );
  }

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-600">
          {columns.map((col) => (
            <th
              key={col.key}
              scope="col"
              className={cx("px-3 py-2 font-medium", ALIGN_CLASSES[col.align ?? "left"])}
            >
              {col.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={rowKey(row)}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            onKeyDown={
              onRowClick
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onRowClick(row);
                    }
                  }
                : undefined
            }
            tabIndex={onRowClick ? 0 : undefined}
            role={onRowClick ? "button" : undefined}
            className={cx(
              "border-b border-neutral-100",
              onRowClick &&
                "cursor-pointer hover:bg-neutral-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-navy-500",
            )}
          >
            {columns.map((col) => (
              <td
                key={col.key}
                className={cx(
                  "px-3 text-navy-900",
                  ALIGN_CLASSES[col.align ?? "left"],
                  DENSITY_CLASSES[density],
                )}
              >
                {col.render
                  ? col.render(row)
                  : String((row as Record<string, unknown>)[col.key] ?? "")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
