"use client";

import { useRef } from "react";
import type { ReactNode } from "react";

import { cx } from "../../utils/cx";
import { useFocusTrap } from "../../utils/useFocusTrap";

export interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Panel width on wide screens; always full width on phones. */
  size?: "sm" | "md" | "lg";
  footer?: ReactNode;
  children: ReactNode;
}

const SIZE_CLASSES: Record<NonNullable<DrawerProps["size"]>, string> = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-md",
  lg: "sm:max-w-xl",
};

/**
 * Right-side slide-over panel (e.g. CQ-029's activity timeline). Same
 * modal contract as `Overlay`: focus trapped inside, Escape and the
 * backdrop close it, focus returns to the opener (`useFocusTrap`).
 */
export function Drawer({ isOpen, onClose, title, size = "md", footer, children }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(panelRef, isOpen, onClose);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        role="presentation"
        data-testid="drawer-backdrop"
        className="absolute inset-0 bg-neutral-950/40"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        tabIndex={-1}
        className={cx(
          "relative z-10 flex h-full w-full flex-col bg-neutral-0 shadow-lg",
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
