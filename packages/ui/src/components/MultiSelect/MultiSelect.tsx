"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { cx } from "../../utils/cx";
import type { SelectOption } from "../Select/Select";

export interface MultiSelectProps {
  label: string;
  options: SelectOption[];
  value: string[];
  onChange: (value: string[]) => void;
  /** Trigger text when nothing is selected. */
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

function summary(options: SelectOption[], value: string[], placeholder: string): string {
  if (value.length === 0) return placeholder;
  if (value.length === 1) {
    return options.find((o) => o.value === value[0])?.label ?? value[0];
  }
  return `${value.length} selected`;
}

/**
 * Multi-value filter picker (e.g. CQ-027's status filter): a trigger
 * button (`aria-expanded`) that opens a popover holding a labelled group of
 * native checkboxes, so keyboard and screen reader behaviour is the
 * browser's own. Escape closes and returns focus to the trigger; a click
 * outside closes. `onChange` receives values in `options` order.
 */
export function MultiSelect({
  label,
  options,
  value,
  onChange,
  placeholder = "Any",
  disabled = false,
  className,
}: MultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverId = useId();
  const labelId = useId();

  useEffect(() => {
    if (!isOpen) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [isOpen]);

  function toggle(optionValue: string) {
    const selected = new Set(value);
    if (selected.has(optionValue)) selected.delete(optionValue);
    else selected.add(optionValue);
    onChange(options.filter((o) => selected.has(o.value)).map((o) => o.value));
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape" && isOpen) {
      e.stopPropagation();
      setIsOpen(false);
      triggerRef.current?.focus();
    }
  }

  return (
    <div
      ref={rootRef}
      className={cx("relative flex flex-col gap-1", className)}
      onKeyDown={onKeyDown}
    >
      <span id={labelId} className="text-sm font-medium text-navy-900">
        {label}
      </span>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-expanded={isOpen}
        aria-controls={isOpen ? popoverId : undefined}
        aria-labelledby={`${labelId} ${popoverId}-summary`}
        onClick={() => setIsOpen((open) => !open)}
        className="flex h-10 items-center justify-between gap-2 rounded-md border border-neutral-200 bg-neutral-0 px-3 text-left text-navy-900 outline-none focus:border-navy-500 disabled:opacity-50"
      >
        <span id={`${popoverId}-summary`}>{summary(options, value, placeholder)}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {isOpen && (
        <div
          id={popoverId}
          role="group"
          aria-labelledby={labelId}
          className="absolute top-full left-0 z-40 mt-1 flex max-h-72 min-w-full flex-col gap-1 overflow-auto rounded-md border border-neutral-200 bg-neutral-0 p-2 shadow-lg"
        >
          {options.map((option, index) => {
            const checkboxId = `${popoverId}-${index}`;
            return (
              <label
                key={option.value}
                htmlFor={checkboxId}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm text-navy-900 hover:bg-navy-50"
              >
                <input
                  id={checkboxId}
                  type="checkbox"
                  checked={value.includes(option.value)}
                  disabled={option.disabled}
                  onChange={() => toggle(option.value)}
                />
                {option.label}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}
