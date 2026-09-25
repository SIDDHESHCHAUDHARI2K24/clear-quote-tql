import { cx } from "../../utils/cx";

// The "check or flag-count" tab headers from the workspace shell (CQ-016).
export interface TabItem {
  id: string;
  label: string;
  status?: "complete" | "flagged" | "pending";
  flagCount?: number;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
}

function TabStatusMark({ item }: { item: TabItem }) {
  if (item.status === "complete") {
    return (
      <span aria-hidden="true" className="text-status-success">
        ✓
      </span>
    );
  }
  if (item.status === "flagged" && item.flagCount && item.flagCount > 0) {
    return (
      <span
        aria-label={`${item.flagCount} flags`}
        className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-status-danger px-1 text-xs text-neutral-0"
      >
        {item.flagCount}
      </span>
    );
  }
  if (item.status === "pending") {
    // spec.md (CQ-016 Application workspace, "Tab rail"): "a grey dot
    // (pending)" for a tab the pipeline hasn't reached yet.
    return <span aria-label="Pending" className="h-2 w-2 rounded-full bg-neutral-300" />;
  }
  return null;
}

export function Tabs({ items, activeId, onChange }: TabsProps) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-neutral-200">
      {items.map((item) => {
        const isActive = item.id === activeId;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            disabled={item.disabled}
            onClick={() => !item.disabled && onChange(item.id)}
            className={cx(
              "flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium",
              isActive
                ? "border-navy-500 text-navy-900"
                : "border-transparent text-neutral-600 hover:text-navy-700",
              item.disabled && "cursor-not-allowed opacity-50",
            )}
          >
            {item.label}
            <TabStatusMark item={item} />
          </button>
        );
      })}
    </div>
  );
}
