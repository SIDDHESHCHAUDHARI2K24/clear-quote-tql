"use client";

import { QuoteBuilder } from "../quote-builder";

export interface QuoteBuilderSlotProps {
  hasStaleQuotes: boolean;
}

// CQ-017 created this slot (plan.md Decision 11) so CQ-017 and CQ-018 never
// edit the same file in one wave. CQ-018 fills it with the quote builder,
// which owns the stale banner and wires its "Re-price" to
// `POST /applications/{id}/reprice`.
export function QuoteBuilderSlot({ hasStaleQuotes }: QuoteBuilderSlotProps) {
  return <QuoteBuilder hasStaleQuotes={hasStaleQuotes} />;
}
