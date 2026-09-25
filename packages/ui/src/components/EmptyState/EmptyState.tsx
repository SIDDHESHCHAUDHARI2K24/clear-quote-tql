import type { ReactNode } from "react";

import { cx } from "../../utils/cx";

export interface EmptyStateProps {
  title: string;
  body?: ReactNode;
  /** Usually a `Button` or a link. */
  action?: ReactNode;
  /** Heading level for `title` (default 2). */
  headingLevel?: 2 | 3;
  className?: string;
}

/** "Nothing here yet" panel for empty lists and first-run screens. */
export function EmptyState({ title, body, action, headingLevel = 2, className }: EmptyStateProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section
      className={cx(
        "flex flex-col items-center gap-2 rounded-lg border border-dashed border-neutral-200 bg-neutral-50 px-6 py-10 text-center",
        className,
      )}
    >
      <Heading className="text-md font-semibold text-navy-900">{title}</Heading>
      {body && <div className="max-w-prose text-sm text-neutral-600">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </section>
  );
}
