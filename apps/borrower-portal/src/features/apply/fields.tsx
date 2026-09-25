"use client";

import { useId } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";

// `@cq/ui`'s `TextField` doesn't link an error via `aria-describedby` on
// its own (its callers, e.g. `SupportForm`, wire that up by hand each
// time); this wizard has many such fields, so `Field` bakes that link in
// once, the same way `@cq/ui`'s own `Select` already does (AC8: "every
// field has a label and its error is linked with aria-describedby").

function cx(...classes: (string | false | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

const INPUT_CLASSES =
  "h-10 rounded-md border border-neutral-200 bg-neutral-0 px-3 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50";

export interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: ReactNode;
  error?: string;
  helperText?: ReactNode;
  id?: string;
}

export function Field({ id, label, error, helperText, className, ...inputProps }: FieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const describedById = error || helperText ? `${fieldId}-description` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={fieldId} className="text-sm font-medium text-navy-900">
        {label}
      </label>
      <input
        id={fieldId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedById}
        className={cx(INPUT_CLASSES, error && "border-status-danger", className)}
        {...inputProps}
      />
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

export interface CheckboxFieldProps {
  id?: string;
  label: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  error?: string;
  disabled?: boolean;
}

export function CheckboxField({
  id,
  label,
  checked,
  onChange,
  error,
  disabled,
}: CheckboxFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const errorId = error ? `${fieldId}-error` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={fieldId} className="flex items-start gap-2 text-sm text-navy-900">
        <input
          id={fieldId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          aria-invalid={error ? true : undefined}
          aria-describedby={errorId}
          className="mt-0.5"
        />
        <span>{label}</span>
      </label>
      {error && (
        <p id={errorId} className="text-xs text-status-danger">
          {error}
        </p>
      )}
    </div>
  );
}
