"use client";

import { useEffect, useRef, useState } from "react";

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
  // PR review round (fresh stage-6): same no-edit-no-override rule as
  // `EnrichedPercentField`, for consistency -- `touched` is set only by
  // the input's own `onChange`. A `ref`, not `useState`: it's read only
  // inside `handleBlur`, so it never needs to trigger a render, and using
  // `useState` here made react-doctor flag it as "state only used in
  // handlers" / "state adjusted after a prop change".
  const touched = useRef(false);

  useEffect(() => {
    setDraft(field?.value ?? "");
    touched.current = false;
  }, [field?.value]);

  const handleChange = (value: string) => {
    setDraft(value);
    touched.current = true;
  };

  const handleBlur = () => {
    if (!touched.current || !field) return;
    touched.current = false;
    if (draft !== "" && draft !== field.value) {
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
