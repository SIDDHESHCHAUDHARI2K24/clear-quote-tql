import type { ChangeEvent } from "react";

import { cx } from "../../utils/cx";
import { SourceBadge } from "../SourceBadge/SourceBadge";
import type { SourceBadgeProps } from "../SourceBadge/SourceBadge";

// value/onChange are decimal strings in percent units, e.g. "7.500" = 7.5%.
// Like MoneyInput, this never parses `value` to a number and never
// reformats what the user typed — display-only, no arithmetic here.
export interface PercentInputProps {
  value: string;
  onChange: (value: string) => void;
  precision?: number;
  disabled?: boolean;
  invalid?: boolean;
  sourceBadge?: SourceBadgeProps;
  "aria-label": string;
}

const DECIMAL_INPUT_PATTERN = /^\d*\.?\d*$/;

export function PercentInput({
  value,
  onChange,
  precision = 3,
  disabled = false,
  invalid = false,
  sourceBadge,
  "aria-label": ariaLabel,
}: PercentInputProps) {
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
      <input
        type="text"
        inputMode="decimal"
        autoComplete="off"
        placeholder={(0).toFixed(precision)}
        className="num flex-1 bg-transparent py-2 text-navy-900 outline-none"
        value={value}
        onChange={handleChange}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-label={ariaLabel}
      />
      <span aria-hidden="true" className="text-neutral-600">
        %
      </span>
      {sourceBadge && <SourceBadge {...sourceBadge} />}
    </div>
  );
}
