"use client";

import { useId, useState } from "react";
import type { ReactNode } from "react";

import { cx } from "../utils/cx";

export interface CollapsibleProps {
  label: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * "See all N options we priced" / "See the full breakdown" (spec.md).
 *
 * CQ-022 AC6 (print): the content always mounts in the DOM -- it's never
 * conditionally rendered based on `isOpen` -- so pure CSS can force it
 * visible under print media regardless of the on-screen open/closed state.
 * This is deliberate: Playwright's `page.pdf()` (AC6's test) renders
 * directly with print media applied and never fires `beforeprint`/
 * `afterprint` or `matchMedia("print")` change events, so a JS "expand
 * before printing" handler would silently do nothing (same for a real
 * browser's "Print to PDF" system action).
 *
 * The closed state uses Tailwind's `.hidden` utility class (`display:
 * none`), not the native HTML `hidden` *attribute* -- verified live against
 * the compiled CSS: Tailwind's own preflight reset for the `hidden`
 * *attribute* is `[hidden]:where(...) { display: none !important; }`, and
 * per the CSS Cascade Layers spec, `!important` declarations invert layer
 * priority (the *earlier* layer wins) -- preflight's `base` layer thus
 * beats *any* `!important` utility in the later `utilities` layer,
 * including a `print:` one, no matter how it's written. `.hidden` (the
 * class) carries no such reset and needs no `!important`: it and
 * `print:block` are two plain, equal-specificity rules in the same
 * `utilities` layer, so the one that's textually later in Tailwind's
 * generated CSS (`print:block`, which sorts after the plain utilities)
 * wins once print media makes it apply, and does nothing otherwise.
 */
export function Collapsible({ label, defaultOpen = false, children }: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className="border-t border-neutral-200 pt-4 print:break-inside-avoid">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={contentId}
        onClick={() => setIsOpen((open) => !open)}
        className="flex w-full items-center justify-between text-left text-sm font-semibold text-navy-700 hover:text-navy-900 print:hidden"
      >
        {label}
        <span aria-hidden="true">{isOpen ? "−" : "+"}</span>
      </button>
      <div id={contentId} className={cx("mt-3 print:block", !isOpen && "hidden")}>
        {children}
      </div>
    </div>
  );
}
