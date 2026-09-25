"use client";

import { useEffect, useState } from "react";

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

  useEffect(() => {
    setDraft(fractionToPercentInputValue(field?.value ?? null));
  }, [field?.value]);

  const handleBlur = () => {
    if (!field || draft === "") return;
    const fraction = percentInputValueToFraction(draft);
    if (fraction !== "" && fraction !== field.value) {
      onOverride(fraction);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-neutral-600">{label}</span>
      <PercentInput
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
