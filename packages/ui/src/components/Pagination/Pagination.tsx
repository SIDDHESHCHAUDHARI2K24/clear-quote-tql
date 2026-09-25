import { cx } from "../../utils/cx";

export interface PaginationProps {
  /** 1-based current page. */
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
  /** Accessible name for the `nav` landmark. */
  label?: string;
  className?: string;
}

const BUTTON_CLASSES =
  "h-8 rounded-md border border-neutral-200 bg-neutral-0 px-3 text-sm text-navy-900 hover:bg-navy-50 disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Previous/next pager for the backend's `Page[T]` responses
 * (`core/pagination.py`: `items`, `total`, `page`, `page_size`). Shows the
 * visible row range ("Showing 26–50 of 212") and "Page 2 of 9".
 */
export function Pagination({
  page,
  pageSize,
  total,
  onChange,
  label = "Pagination",
  className,
}: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  const current = Math.min(Math.max(1, page), pageCount);
  const first = total === 0 ? 0 : (current - 1) * pageSize + 1;
  const last = Math.min(total, current * pageSize);

  return (
    <nav
      aria-label={label}
      className={cx("flex flex-wrap items-center justify-between gap-2 text-sm", className)}
    >
      <p className="text-neutral-600" aria-live="polite">
        {total === 0 ? "No results" : `Showing ${first}–${last} of ${total}`}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={BUTTON_CLASSES}
          disabled={current <= 1}
          onClick={() => onChange(current - 1)}
        >
          Previous
        </button>
        <span className="text-neutral-600">
          Page {current} of {pageCount}
        </span>
        <button
          type="button"
          className={BUTTON_CLASSES}
          disabled={current >= pageCount}
          onClick={() => onChange(current + 1)}
        >
          Next
        </button>
      </div>
    </nav>
  );
}
