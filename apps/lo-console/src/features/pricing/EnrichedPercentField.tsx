"use client";

import { PercentInput } from "@cq/ui";
import type { SourceBadgeSource } from "@cq/ui";

import { fractionToPercentInputValue, percentInputValueToFraction } from "./format";
import type { PricingField } from "./api";
import { useTouchedDraft } from "./useTouchedDraft";

export interface EnrichedPercentFieldProps {
  label: string;
  ariaLabel: string;
  field: PricingField | undefined;
  onOverride: (value: string) => void;
  onRevert: () => void;
  disabled?: boolean;
}

// A committable draft resolves through the same percent<->fraction
// conversion `format.ts` documents; `""` (an empty/unparseable draft) is
// "not committable" for `useTouchedDraft.commit`.
function percentToWire(draftValue: string): string | null {
  const fraction = percentInputValueToFraction(draftValue);
  return fraction === "" ? null : fraction;
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
  // PR review round (fresh stage-6, CRITICAL, then a second pass): the
  // original `handleBlur` fired `onOverride` whenever the round-tripped
  // display value didn't strictly equal `field.value` -- lossy for small
  // rates ("0.000089" -> "0.0001"), so a plain focus+blur with no edit
  // silently overrode the field. `useTouchedDraft` only ever commits after
  // a real edit (its `touched` ref, set only by `handleChange`), and
  // `commit`'s numeric (not string) comparison against `field.value`
  // means retyping the same rate in a different-looking format (e.g.
  // "0.64" over a field displaying "0.640") is correctly a no-op too --
  // see `useTouchedDraft.ts` and this fix's tests for both cases.
  const { draft, handleChange, commit } = useTouchedDraft(
    field?.value,
    fractionToPercentInputValue,
  );

  const handleBlur = () => {
    const fraction = commit(percentToWire);
    if (fraction !== null) {
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
