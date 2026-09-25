import type { ReactNode } from "react";

import { cx } from "../../utils/cx";

export interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;
  padding?: "sm" | "md" | "lg";
  children: ReactNode;
}

const PADDING_CLASSES: Record<NonNullable<CardProps["padding"]>, string> = {
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
};

export function Card({ title, actions, padding = "md", children }: CardProps) {
  return (
    <section
      className={cx(
        "rounded-lg border border-neutral-200 bg-neutral-0 shadow-sm",
        PADDING_CLASSES[padding],
      )}
    >
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title && <h3 className="text-md font-semibold text-navy-900">{title}</h3>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
