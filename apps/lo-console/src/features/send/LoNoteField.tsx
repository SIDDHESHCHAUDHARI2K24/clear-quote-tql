"use client";

import { useId, useState } from "react";

export const LO_NOTE_MAX = 500;

export interface LoNoteFieldProps {
  value: string;
  disabled?: boolean;
  /** Called on blur when the text changed. */
  onSave: (note: string) => void;
}

/** The LO's optional note, shown under "What we recommend". Remount with a
 * `key` to reset it from the server. */
export function LoNoteField({ value, disabled = false, onSave }: LoNoteFieldProps) {
  const id = useId();
  const [text, setText] = useState(value);
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-semibold text-navy-900">
        Note to the borrower (optional)
      </label>
      <textarea
        id={id}
        rows={3}
        maxLength={LO_NOTE_MAX}
        disabled={disabled}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => {
          if (text !== value) onSave(text);
        }}
        className="rounded-md border border-neutral-300 px-3 py-2 text-sm text-navy-900 focus:border-navy-500 focus:outline-none"
      />
      <span className="num self-end text-xs text-neutral-600" aria-live="polite">
        {text.length}/{LO_NOTE_MAX}
      </span>
    </div>
  );
}
