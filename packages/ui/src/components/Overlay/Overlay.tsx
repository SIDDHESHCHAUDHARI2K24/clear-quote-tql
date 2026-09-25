"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { cx } from "../../utils/cx";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) return [];
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

export interface OverlayProps {
  isOpen: boolean;
  onClose: () => void;
  title: ReactNode;
  size?: "sm" | "md" | "lg" | "full";
  footer?: ReactNode;
  children: ReactNode;
}

const SIZE_CLASSES: Record<NonNullable<OverlayProps["size"]>, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  full: "max-w-full h-full",
};

export function Overlay({ isOpen, onClose, title, size = "md", footer, children }: OverlayProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  // Focus trap + return-focus-on-close (docs/backlog/CQ-005-frontend-skeleton/
  // post-dev.md's known gap, fixed by CQ-016 since CQ-018/CQ-024 dialogs
  // depend on it): on open, remember whatever had focus and move focus into
  // the dialog; on close (including unmount), focus returns to whatever had
  // it before the dialog opened.
  //
  // Deliberately its own effect, keyed only on `isOpen` -- not also on
  // `onClose` (see the effect below). A consumer's `onClose` is very often
  // a fresh closure on every render (e.g. it reads other local state), and
  // this effect's cleanup re-focuses the dialog's first element on every
  // re-run: keying it to `onClose` too would re-steal focus away from
  // whatever the user is doing (like typing in a field inside the dialog)
  // on every keystroke -- and since the first focusable element is often a
  // button, a later space/enter keystroke would then "click" it and close
  // the dialog out from under the user. Caught by
  // `StatusActionsMenu.test.tsx` (CQ-016) typing into its reason field.
  useEffect(() => {
    if (!isOpen) return;

    previouslyFocusedRef.current = document.activeElement as HTMLElement | null;
    const focusable = getFocusableElements(dialogRef.current);
    (focusable[0] ?? dialogRef.current)?.focus();

    return () => {
      previouslyFocusedRef.current?.focus?.();
      previouslyFocusedRef.current = null;
    };
  }, [isOpen]);

  // Escape-to-close + Tab/Shift+Tab wrap within the dialog's focusable
  // elements instead of escaping to the page behind it. Safe to re-attach
  // on every `onClose` change -- unlike the effect above, it has no focus
  // side effect of its own.
  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      const elements = getFocusableElements(dialogRef.current);
      if (elements.length === 0) return;
      const first = elements[0];
      const last = elements[elements.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        role="presentation"
        data-testid="overlay-backdrop"
        className="absolute inset-0 bg-neutral-950/40"
        onClick={onClose}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        tabIndex={-1}
        className={cx(
          "relative z-10 flex max-h-[90vh] w-full flex-col rounded-lg bg-neutral-0 shadow-lg",
          SIZE_CLASSES[size],
        )}
      >
        <header className="flex items-center justify-between border-b border-neutral-200 px-4 py-3">
          <h2 className="text-md font-semibold text-navy-900">{title}</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-600 hover:bg-neutral-100"
          >
            ✕
          </button>
        </header>
        <div className="flex-1 overflow-auto px-4 py-3">{children}</div>
        {footer && <footer className="border-t border-neutral-200 px-4 py-3">{footer}</footer>}
      </div>
    </div>
  );
}
