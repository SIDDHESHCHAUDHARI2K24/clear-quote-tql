"use client";

import { useId } from "react";
import type { ReactNode, SelectHTMLAttributes } from "react";

import { cx } from "../../utils/cx";

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "onChange" | "value" | "children"
> {
  label: ReactNode;
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  /** Adds a first, empty option (value `""`) with this text, e.g. "Any". */
  placeholder?: string;
  error?: ReactNode;
  helperText?: ReactNode;
}

const SELECT_CLASSES =
  "h-10 rounded-md border border-neutral-200 bg-neutral-0 px-3 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50";

/**
 * A labelled native `<select>` (native for free keyboard, mobile and screen
 * reader support). `error`/`helperText` are linked via `aria-describedby`.
 */
export function Select({
  id,
  label,
  options,
  value,
  onChange,
  placeholder,
  error,
  helperText,
  className,
  ...selectProps
}: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const describedById = error || helperText ? `${selectId}-description` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={selectId} className="text-sm font-medium text-navy-900">
        {label}
      </label>
      <select
        id={selectId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedById}
        className={cx(SELECT_CLASSES, Boolean(error) && "border-status-danger", className)}
        {...selectProps}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      {(error || helperText) && (
        <p
          id={describedById}
          className={cx("text-xs", error ? "text-status-danger" : "text-neutral-600")}
        >
          {error ?? helperText}
        </p>
      )}
    </div>
  );
}
