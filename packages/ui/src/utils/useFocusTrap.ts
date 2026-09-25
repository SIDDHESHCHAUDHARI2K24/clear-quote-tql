"use client";

import { useEffect, useRef } from "react";
import type { RefObject } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) return [];
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

/**
 * Focus trap + Escape-to-close + return-focus-on-close for a modal surface
 * (`Overlay`, `Drawer`). Extracted from `Overlay` by the P5/P6 foundation
 * (E7) so every modal surface shares one implementation.
 *
 * - On open: remembers whatever had focus and moves focus to the first
 *   focusable element inside `containerRef` (or the container itself).
 * - While open: Tab/Shift+Tab wrap within the container's focusable
 *   elements; Escape calls `onClose`.
 * - On close/unmount: focus returns to whatever had it before opening.
 *
 * The initial-focus effect is keyed only on `isOpen`, never `onClose`: a
 * consumer's `onClose` is often a fresh closure every render, and
 * re-running the focus effect on each render would steal focus back to the
 * first element while the user types (CQ-016 regression, see
 * `Overlay.test.tsx`).
 */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  isOpen: boolean,
  onClose: () => void,
): void {
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    previouslyFocusedRef.current = document.activeElement as HTMLElement | null;
    const focusable = getFocusableElements(containerRef.current);
    (focusable[0] ?? containerRef.current)?.focus();

    return () => {
      previouslyFocusedRef.current?.focus?.();
      previouslyFocusedRef.current = null;
    };
    // containerRef is a stable ref object; only open/close re-runs this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      const elements = getFocusableElements(containerRef.current);
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
  }, [containerRef, isOpen, onClose]);
}
