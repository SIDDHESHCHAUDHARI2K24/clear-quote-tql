"use client";

import { MoneyInput } from "@cq/ui";
import type { SourceBadgeSource } from "@cq/ui";

import type { PricingField } from "./api";
import { useTouchedDraft } from "./useTouchedDraft";

export interface EnrichedMoneyFieldProps {
  label: string;
  ariaLabel: string;
  field: PricingField | undefined;
  onOverride: (value: string) => void;
  onRevert: () => void;
  disabled?: boolean;
}

// `MoneyInput`'s value/onChange are already the wire value's own display
// text (no unit conversion) -- a stable, module-level reference so
// `useTouchedDraft`'s reset effect doesn't re-run every render.
function moneyDisplay(value: string | null): string {
  return value ?? "";
}

// A committable draft is just itself -- money has no display-unit
// conversion to invert (unlike `EnrichedPercentField`'s percent<->fraction
// scale).
function moneyToWire(draftValue: string): string {
  return draftValue;
}

// One badge-carrying enriched money field (taxes-as-dollars isn't shown
// this way, but insurance/HOA/LTR-rent/STR-revenue are): a `MoneyInput`
// that's always editable (spec.md's "click -> inline edit" -- plan.md
// Decision 10) with its `SourceBadge` inline, showing "LO override" plus a
// revert affordance once overridden. Commits an override on blur, only
// when the typed value actually changed (`useTouchedDraft` -- PR #9
// review: no-edit-no-override, applied here for consistency with
// `EnrichedPercentField`).
export function EnrichedMoneyField({
  label,
  ariaLabel,
  field,
  onOverride,
  onRevert,
  disabled = false,
}: EnrichedMoneyFieldProps) {
  const { draft, handleChange, commit } = useTouchedDraft(field?.value, moneyDisplay);

  const handleBlur = () => {
    const wire = commit(moneyToWire);
    if (wire !== null) {
      onOverride(wire);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      {/* Not a <label for=...> -- MoneyInput's own aria-label already gives
          the input its accessible name; this is a purely visual caption. */}
      <span className="text-xs font-medium text-neutral-600">{label}</span>
      <MoneyInput
        value={draft}
        onChange={handleChange}
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
