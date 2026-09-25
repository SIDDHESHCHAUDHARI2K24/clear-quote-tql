"use client";

export interface QuoteBuilderSlotProps {
  hasStaleQuotes: boolean;
}

// CQ-017 owns only this stale banner + placeholder; CQ-018 replaces the
// placeholder body with the real quote cards/overlay/AutoQuote UI and wires
// the "Re-price" button (spec.md: "the action itself is wired in CQ-018").
// Kept in its own file (plan.md Decision 11) so CQ-017 and CQ-018 never
// edit the same file in the same wave.
export function QuoteBuilderSlot({ hasStaleQuotes }: QuoteBuilderSlotProps) {
  return (
    <div className="flex flex-col gap-3">
      {hasStaleQuotes && (
        <div
          role="status"
          className="flex items-center justify-between gap-3 rounded-md border border-status-warning bg-status-warning/10 px-4 py-3 text-sm text-navy-900"
        >
          <span>Quotes are out of date — Re-price</span>
          <button
            type="button"
            disabled
            title="Arrives in CQ-018"
            aria-label="Re-price"
            className="rounded-md border border-neutral-300 px-3 py-1 text-sm font-medium text-neutral-500 opacity-60"
          >
            Re-price
          </button>
        </div>
      )}
      <div className="rounded-lg border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-500">
        Quote builder arrives in CQ-018.
      </div>
    </div>
  );
}
