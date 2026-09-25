"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";

import { cx } from "../../utils/cx";

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
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
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
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
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
