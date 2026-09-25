"use client";

import type { InputHTMLAttributes, ReactNode } from "react";

import { cx } from "../utils/cx";

export interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: ReactNode;
  helperText?: ReactNode;
}

const INPUT_CLASSES =
  "rounded-md border border-neutral-200 bg-neutral-0 px-3 py-2 text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50";

// Shared by every auth form (CredentialsForm, SignupForm, OtpForm): label
// plus input with the className every one of the old per-app copies pasted
// verbatim. Forwards the rest of the standard input props (type,
// autoComplete, inputMode, maxLength, ...) so callers configure the input
// the same way they would a plain <input>.
export function TextField({ id, label, helperText, className, ...inputProps }: TextFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-navy-900">
        {label}
      </label>
      <input id={id} className={cx(INPUT_CLASSES, className)} {...inputProps} />
      {helperText && <p className="text-xs text-neutral-500">{helperText}</p>}
    </div>
  );
}
