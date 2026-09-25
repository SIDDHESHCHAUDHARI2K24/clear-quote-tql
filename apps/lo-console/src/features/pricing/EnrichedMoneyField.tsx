"use client";

import { useEffect, useState } from "react";

import { MoneyInput } from "@cq/ui";
import type { SourceBadgeSource } from "@cq/ui";

import type { PricingField } from "./api";

export interface EnrichedMoneyFieldProps {
  label: string;
  ariaLabel: string;
  field: PricingField | undefined;
  onOverride: (value: string) => void;
  onRevert: () => void;
  disabled?: boolean;
}

// One badge-carrying enriched money field (taxes-as-dollars isn't shown
// this way, but insurance/HOA/LTR-rent/STR-revenue are): a `MoneyInput`
// that's always editable (spec.md's "click -> inline edit" -- plan.md
// Decision 10) with its `SourceBadge` inline, showing "LO override" plus a
// revert affordance once overridden. Commits an override on blur, only
// when the typed value actually changed.
export function EnrichedMoneyField({
  label,
  ariaLabel,
  field,
  onOverride,
  onRevert,
  disabled = false,
}: EnrichedMoneyFieldProps) {
  const [draft, setDraft] = useState(field?.value ?? "");

  useEffect(() => {
    setDraft(field?.value ?? "");
  }, [field?.value]);

  const handleBlur = () => {
    if (field && draft !== "" && draft !== field.value) {
      onOverride(draft);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      {/* Not a <label for=...> -- MoneyInput's own aria-label already gives
          the input its accessible name; this is a purely visual caption. */}
      <span className="text-xs font-medium text-neutral-600">{label}</span>
      <MoneyInput
        value={draft}
        onChange={setDraft}
        onBlur={handleBlur}
        disabled={disabled || !field}
        aria-label={ariaLabel}
        sourceBadge={
          field
            ? {
                source: field.source as SourceBadgeSource,
                onRevert: field.overridden ? onRevert : undefined,
              }
            : undefined
        }
      />
    </div>
  );
}
