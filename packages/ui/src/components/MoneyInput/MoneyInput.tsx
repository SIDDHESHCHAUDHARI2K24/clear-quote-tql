import type { ChangeEvent } from "react";

import { cx } from "../../utils/cx";
import { SourceBadge } from "../SourceBadge/SourceBadge";
import type { SourceBadgeProps } from "../SourceBadge/SourceBadge";

// value/onChange are decimal strings, e.g. "342000.00"; '' when empty.
// This component never parses `value` to a number: no arithmetic, no
// reformatting of what the user typed. Money math lives only in
// quote_engine (Decimal), per AGENTS.md.
export interface MoneyInputProps {
  value: string;
  onChange: (value: string) => void;
  currency?: "USD";
  disabled?: boolean;
  invalid?: boolean;
  sourceBadge?: SourceBadgeProps;
  "aria-label": string;
}

// Allows a plain decimal string while typing: digits with at most one
// decimal point. Rejects anything else (letters, multiple dots, commas) so
// the field never holds a value it can't emit unmodified.
const DECIMAL_INPUT_PATTERN = /^\d*\.?\d*$/;

export function MoneyInput({
  value,
  onChange,
  currency = "USD",
  disabled = false,
  invalid = false,
  sourceBadge,
  "aria-label": ariaLabel,
}: MoneyInputProps) {
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw === "" || DECIMAL_INPUT_PATTERN.test(raw)) {
      onChange(raw);
    }
  };

  return (
    <div
      className={cx(
        "flex items-center gap-2 rounded-md border bg-neutral-0 px-2",
        invalid ? "border-status-danger" : "border-neutral-200",
        disabled && "opacity-50",
      )}
    >
      <span aria-hidden="true" className="num text-neutral-600">
        {currency === "USD" ? "$" : currency}
      </span>
      <input
        type="text"
        inputMode="decimal"
        autoComplete="off"
        className="num flex-1 bg-transparent py-2 text-navy-900 outline-none"
        value={value}
        onChange={handleChange}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-label={ariaLabel}
      />
      {sourceBadge && <SourceBadge {...sourceBadge} />}
    </div>
  );
}
