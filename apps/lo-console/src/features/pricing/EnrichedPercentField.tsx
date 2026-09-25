"use client";

import { useEffect, useRef, useState } from "react";

import { PercentInput } from "@cq/ui";
import type { SourceBadgeSource } from "@cq/ui";

import { fractionToPercentInputValue, percentInputValueToFraction } from "./format";
import type { PricingField } from "./api";

export interface EnrichedPercentFieldProps {
  label: string;
  ariaLabel: string;
  field: PricingField | undefined;
  onOverride: (value: string) => void;
  onRevert: () => void;
  disabled?: boolean;
}

// Same shape as `EnrichedMoneyField`, for the one badge-carrying pricing
// field that's a rate rather than a dollar amount (`property_tax_annual_
// rate`). `field.value` on the wire is a 0-1 fraction; `PercentInput`
// displays/edits percent-unit text -- `format.ts`'s two conversion helpers
// are the single place that translates between them (a unit conversion of
// the input control's own contract, not a derived financial figure).
export function EnrichedPercentField({
  label,
  ariaLabel,
  field,
  onOverride,
  onRevert,
  disabled = false,
}: EnrichedPercentFieldProps) {
  const [draft, setDraft] = useState(() => fractionToPercentInputValue(field?.value ?? null));
  // PR review round (fresh stage-6, CRITICAL): the old `handleBlur` fired
  // `onOverride` whenever the round-tripped display value didn't strictly
  // equal `field.value` -- but `fractionToPercentInputValue` (x100,
  // .toFixed(3)) then `percentInputValueToFraction` (/100, .toFixed(4)) is
  // lossy for small rates ("0.000089" -> "0.0001"), so a plain focus+blur
  // with no edit silently overrode the field. `touched` is set only by the
  // input's own `onChange`, so a no-edit blur is a true no-op regardless of
  // any display rounding. A `ref`, not `useState`: it's read only inside
  // `handleBlur`, so it never needs to trigger a render.
  const touched = useRef(false);

  useEffect(() => {
    setDraft(fractionToPercentInputValue(field?.value ?? null));
    touched.current = false;
  }, [field?.value]);

  const handleChange = (value: string) => {
    setDraft(value);
    touched.current = true;
  };

  const handleBlur = () => {
    if (!touched.current || !field || draft === "") return;
    touched.current = false;
    // Compare the user's typed text to what this field's current value
    // would itself display -- not the round-tripped fraction -- so a typed
    // value that merely re-displays the same rate (e.g. re-typing "0.640"
    // over "0.0064") is correctly treated as no change either.
    if (draft === fractionToPercentInputValue(field.value)) return;
    const fraction = percentInputValueToFraction(draft);
    if (fraction !== "") {
      onOverride(fraction);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-neutral-600">{label}</span>
      <PercentInput
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
