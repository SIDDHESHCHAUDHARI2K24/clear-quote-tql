"use client";

import { useId, useState } from "react";
import type { ReactNode } from "react";

export interface CollapsibleProps {
  label: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** "See all N options we priced" / "See the full breakdown" (spec.md). */
export function Collapsible({ label, defaultOpen = false, children }: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className="border-t border-neutral-200 pt-4">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={contentId}
        onClick={() => setIsOpen((open) => !open)}
        className="flex w-full items-center justify-between text-left text-sm font-semibold text-navy-700 hover:text-navy-900"
      >
        {label}
        <span aria-hidden="true">{isOpen ? "−" : "+"}</span>
      </button>
      {isOpen && (
        <div id={contentId} className="mt-3">
          {children}
        </div>
      )}
    </div>
  );
}
